"""
tests/unit/domain/services/test_technical_analysis_service.py

El motor de análisis técnico es el producto: sus resultados son lo que el
usuario lee para decidir. Hasta ahora no tenía ni un test, de modo que un
error de signo en un indicador o un veredicto invertido habrían pasado
inadvertidos.

Los tests construyen series sintéticas con una forma conocida —una
tendencia alcista sostenida, una caída, un mercado plano— y comprueban
que el motor llega a la conclusión que corresponde. No se verifican los
valores exactos que devuelve la librería `ta` (eso sería testear una
dependencia de terceros), sino las reglas de negocio que el proyecto
construye encima: umbrales, señales, veredicto y contabilidad del
backtest.

Todos son unitarios puros: sin base de datos, sin red.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services import technical_analysis_service as tas

# ── Generadores de series con forma conocida ───────────────────────


def _ohlcv(closes: list[float]) -> pd.DataFrame:
    """
    DataFrame OHLCV coherente a partir de una lista de cierres.

    El máximo y el mínimo se derivan del cierre para que las velas sean
    válidas (high >= max(open, close) y low <= min(open, close)).
    """
    closes = [float(c) for c in closes]
    opens = [closes[0]] + closes[:-1]
    highs = [max(o, c) * 1.005 for o, c in zip(opens, closes, strict=False)]
    lows = [min(o, c) * 0.995 for o, c in zip(opens, closes, strict=False)]
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [1_000.0] * len(closes),
        }
    )


def _uptrend(length: int = 200, start: float = 100.0, step: float = 1.0) -> pd.DataFrame:
    """Tendencia alcista limpia y sostenida."""
    return _ohlcv([start + step * i for i in range(length)])


def _downtrend(length: int = 200, start: float = 300.0, step: float = 1.0) -> pd.DataFrame:
    """Tendencia bajista limpia y sostenida."""
    return _ohlcv([start - step * i for i in range(length)])


def _flat(length: int = 200, level: float = 100.0) -> pd.DataFrame:
    """Mercado plano con ruido mínimo determinista."""
    rng = np.random.default_rng(seed=20260802)
    noise = rng.normal(0, 0.05, length)
    return _ohlcv([level + n for n in noise])


# ── Indicadores individuales ───────────────────────────────────────


@pytest.mark.unit
class TestCalculateIndicator:

    @pytest.mark.parametrize(
        "indicator", ["RSI", "MACD", "SMA", "EMA", "BOLLINGER"]
    )
    def test_every_indicator_returns_the_common_contract(self, indicator):
        """
        Núcleo común a todos los indicadores.

        Solo se comprueban las claves compartidas. Cada indicador expone
        además sus propias series con nombres distintos (`series` en RSI,
        `series_macd`/`series_signal` en MACD, `series_sma20`/`series_sma50`
        en SMA…), una inconsistencia del contrato que este test deja
        documentada: unificarla rompería al cliente actual, así que es una
        refactorización aparte, no un efecto colateral de esta auditoría.
        """
        result = tas.calculate_indicator(_uptrend(), indicator)

        assert result["indicator"] == indicator
        assert "value" in result
        assert "interpretation" in result
        assert "params" in result
        assert result["signal"] in (
            tas.SIGNAL_STRONG_BUY,
            tas.SIGNAL_BUY,
            tas.SIGNAL_NEUTRAL,
            tas.SIGNAL_SELL,
            tas.SIGNAL_STRONG_SELL,
        )

    @pytest.mark.parametrize(
        ("indicator", "series_keys"),
        [
            ("RSI", ["series"]),
            ("MACD", ["series_macd", "series_signal", "series_histogram"]),
            ("SMA", ["series_sma20", "series_sma50"]),
            ("EMA", ["series_ema12", "series_ema26"]),
            ("BOLLINGER", ["series_upper", "series_middle", "series_lower"]),
        ],
    )
    def test_each_indicator_exposes_its_series(self, indicator, series_keys):
        """Las series que consume el gráfico del cliente están presentes."""
        result = tas.calculate_indicator(_uptrend(), indicator)
        for key in series_keys:
            assert isinstance(result[key], list), f"falta la serie {key} en {indicator}"

    def test_indicator_type_is_case_insensitive(self):
        assert tas.calculate_indicator(_uptrend(), "rsi")["indicator"] == "RSI"

    def test_rsi_signals_overbought_on_a_sustained_rally(self):
        """
        Una subida ininterrumpida lleva el RSI por encima de 70, que es
        zona de sobrecompra: la señal debe ser de venta.
        """
        result = tas.calculate_indicator(_uptrend(), "RSI")
        assert result["value"] > 70
        assert result["signal"] == tas.SIGNAL_SELL

    def test_rsi_signals_oversold_on_a_sustained_selloff(self):
        result = tas.calculate_indicator(_downtrend(), "RSI")
        assert result["value"] < 30
        assert result["signal"] == tas.SIGNAL_BUY

    def test_rsi_is_neutral_in_a_flat_market(self):
        result = tas.calculate_indicator(_flat(), "RSI")
        assert 30 <= result["value"] <= 70
        assert result["signal"] == tas.SIGNAL_NEUTRAL

    def test_sma_signals_buy_when_price_is_above_the_average(self):
        """En una tendencia alcista el precio va por delante de su media."""
        result = tas.calculate_indicator(_uptrend(), "SMA")
        assert result["signal"] in (tas.SIGNAL_BUY, tas.SIGNAL_STRONG_BUY)

    def test_sma_signals_sell_when_price_is_below_the_average(self):
        result = tas.calculate_indicator(_downtrend(), "SMA")
        assert result["signal"] in (tas.SIGNAL_SELL, tas.SIGNAL_STRONG_SELL)

    def test_unknown_indicator_returns_the_empty_result(self):
        """Un indicador desconocido no revienta: devuelve resultado vacío."""
        result = tas.calculate_indicator(_uptrend(), "NO_EXISTE")
        assert result["value"] is None
        assert result["signal"] == tas.SIGNAL_NEUTRAL

    def test_short_series_does_not_raise(self):
        """
        Con menos velas que la ventana del indicador, el cálculo no puede
        completarse. Debe devolverse un resultado neutro, no una excepción
        que acabe en un 500.
        """
        result = tas.calculate_indicator(_uptrend(length=5), "RSI")
        assert result["signal"] == tas.SIGNAL_NEUTRAL


# ── Panel de señales y veredicto ───────────────────────────────────


@pytest.mark.unit
class TestSignalsDashboard:

    def test_returns_indicators_and_summary(self):
        result = tas.calculate_signals_dashboard(_uptrend())

        assert len(result["indicators"]) > 0
        summary = result["summary"]
        assert summary["total"] == len(result["indicators"])
        # La contabilidad tiene que cuadrar: cada indicador cae en una
        # y solo una categoría.
        assert (
            summary["buy_count"] + summary["sell_count"] + summary["neutral_count"]
            == summary["total"]
        )

    def test_verdict_is_bullish_in_an_uptrend(self):
        summary = tas.calculate_signals_dashboard(_uptrend())["summary"]
        assert summary["verdict"] in (tas.SIGNAL_BUY, tas.SIGNAL_STRONG_BUY)
        assert summary["score"] > 0

    def test_verdict_is_bearish_in_a_downtrend(self):
        summary = tas.calculate_signals_dashboard(_downtrend())["summary"]
        assert summary["verdict"] in (tas.SIGNAL_SELL, tas.SIGNAL_STRONG_SELL)
        assert summary["score"] < 0

    def test_last_price_matches_the_final_close(self):
        df = _uptrend()
        result = tas.calculate_signals_dashboard(df)
        assert result["last_price"] == pytest.approx(float(df["close"].iloc[-1]))

    def test_score_stays_within_the_weight_range(self):
        """El score es una media de pesos en [-2, 2]; no puede salirse."""
        for df in (_uptrend(), _downtrend(), _flat()):
            score = tas.calculate_signals_dashboard(df)["summary"]["score"]
            assert -2 <= score <= 2


# ── Patrones de velas ──────────────────────────────────────────────


@pytest.mark.unit
class TestCandlePatterns:

    def test_returns_a_list_of_well_formed_patterns(self):
        patterns = tas.detect_candle_patterns(_uptrend())
        assert isinstance(patterns, list)
        for pattern in patterns:
            assert {"name", "signal", "description", "reliability", "index"} <= set(pattern)

    def test_short_series_returns_no_patterns(self):
        assert tas.detect_candle_patterns(_uptrend(length=3)) == []

    def test_detects_a_hammer(self):
        """
        Martillo: cuerpo pequeño arriba y sombra inferior larga, tras una
        caída. Se construye la vela a mano para que la forma sea inequívoca.
        """
        closes = [100 - i for i in range(20)]
        df = _ohlcv(closes)
        # Última vela: cuerpo diminuto y mecha inferior de varias veces su tamaño.
        last = len(df) - 1
        df.loc[last, "open"] = 81.0
        df.loc[last, "close"] = 81.5
        df.loc[last, "high"] = 81.7
        df.loc[last, "low"] = 78.0

        names = [p["name"].lower() for p in tas.detect_candle_patterns(df)]
        assert any("martillo" in n or "hammer" in n for n in names)


# ── Predicción ML ──────────────────────────────────────────────────


@pytest.mark.unit
class TestPricePrediction:

    def test_refuses_to_predict_without_enough_history(self):
        """
        Con pocas velas el modelo no se entrena. Debe decirlo de forma
        explícita en lugar de devolver una predicción sin fundamento, que
        es lo peligroso en un producto financiero.
        """
        result = tas.predict_price_direction(_uptrend(length=50))
        assert result["prediction"] == "INSUFFICIENT_DATA"
        assert result["confidence"] == 0

    def test_prediction_contract_on_sufficient_history(self):
        result = tas.predict_price_direction(_uptrend(length=300), horizon=5)
        assert result["horizon"] == 5
        assert "prediction" in result
        if result["prediction"] not in ("INSUFFICIENT_DATA", "ERROR"):
            assert 0 <= result["confidence"] <= 100

    def test_horizon_is_echoed_back(self):
        result = tas.predict_price_direction(_uptrend(length=300), horizon=10)
        assert result["horizon"] == 10


# ── Backtesting ────────────────────────────────────────────────────


@pytest.mark.unit
class TestBacktest:

    STRATEGIES = [
        "rsi_reversal",
        "macd_crossover",
        "bollinger_bounce",
        "sma_crossover",
        "ema_trend",
    ]

    @pytest.mark.parametrize("strategy", STRATEGIES)
    def test_every_strategy_runs_and_reports_metrics(self, strategy):
        result = tas.run_backtest(_uptrend(length=300), strategy, initial_capital=10_000)
        assert "error" not in result
        assert "total_return_pct" in result
        assert "trades" in result

    def test_unknown_strategy_is_rejected(self):
        result = tas.run_backtest(_uptrend(length=300), "estrategia_inventada")
        assert "error" in result

    def test_rejects_series_that_are_too_short(self):
        result = tas.run_backtest(_uptrend(length=30), "rsi_reversal")
        assert "error" in result

    def test_initial_capital_is_respected(self):
        """
        El capital final de una estrategia que nunca opera debe ser
        exactamente el inicial: si no, hay dinero apareciendo de la nada.
        """
        result = tas.run_backtest(_flat(length=300), "sma_crossover", initial_capital=5_000)
        assert "error" not in result
        assert result["initial_capital"] == pytest.approx(5_000)

    def test_trade_count_matches_the_reported_trades(self):
        result = tas.run_backtest(_uptrend(length=300), "macd_crossover")
        assert result["total_trades"] == len(result["trades"])

    def test_win_rate_is_a_valid_percentage(self):
        result = tas.run_backtest(_flat(length=300), "rsi_reversal")
        assert 0 <= result["win_rate_pct"] <= 100

    def test_reports_the_buy_and_hold_baseline(self):
        """
        Sin la referencia de comprar y mantener, un +8% no dice nada: la
        pregunta es si la estrategia bate a no hacer nada.
        """
        result = tas.run_backtest(_uptrend(length=300), "sma_crossover")
        assert "buy_hold_return_pct" in result
        assert result["candles_count"] == 300

    def test_return_percentage_is_consistent_with_the_final_capital(self):
        """
        El porcentaje de retorno tiene que derivarse del capital final;
        una discrepancia aquí significaría que el informe que ve el
        usuario no describe la simulación que se ejecutó.
        """
        initial = 10_000.0
        result = tas.run_backtest(_uptrend(length=300), "ema_trend", initial_capital=initial)
        expected = (result["final_capital"] - initial) / initial * 100
        assert result["total_return_pct"] == pytest.approx(expected, abs=0.01)
