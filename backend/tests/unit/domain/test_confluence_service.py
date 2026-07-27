"""
tests/unit/domain/test_confluence_service.py — Tests del motor de confluencia.

Datos OHLCV sintéticos y deterministas (tendencia + onda senoidal que
genera pivotes regulares): sin red, sin BD, sin aleatoriedad.
"""

import math

import pandas as pd
import pytest

from core.domain.services.confluence_service import (
    TREND_DOWN,
    TREND_SIDEWAYS,
    TREND_UP,
    build_confluence_card,
    calculate_fibonacci_levels,
    calculate_support_resistance,
    classify_trend,
)


def make_ohlcv_df(rows: int = 260, start: float = 100.0, drift: float = 0.0,
                  wave: float = 8.0, period: int = 20) -> pd.DataFrame:
    """OHLCV sintético: deriva lineal + onda senoidal (pivotes cada `period`)."""
    closes = [
        start + drift * i + wave * math.sin(2 * math.pi * i / period)
        for i in range(rows)
    ]
    return pd.DataFrame({
        "timestamp": [1700000000000 + i * 86_400_000 for i in range(rows)],
        "open": [c * 0.995 for c in closes],
        "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes],
        "close": closes,
        "volume": [1000.0 + i for i in range(rows)],
    })


class TestSupportResistance:

    @pytest.mark.unit
    def test_supports_below_and_resistances_above_price(self):
        df = make_ohlcv_df(drift=0.0)  # mercado lateral: pivotes a ambos lados
        sr = calculate_support_resistance(df)
        last_price = float(df["close"].iloc[-1])

        assert sr["supports"], "Un mercado lateral debe tener soportes detectados"
        assert sr["resistances"], "Un mercado lateral debe tener resistencias detectadas"
        assert all(s["level"] < last_price for s in sr["supports"])
        assert all(r["level"] > last_price for r in sr["resistances"])

    @pytest.mark.unit
    def test_levels_sorted_by_proximity(self):
        df = make_ohlcv_df(drift=0.0)
        sr = calculate_support_resistance(df)

        support_levels = [s["level"] for s in sr["supports"]]
        resistance_levels = [r["level"] for r in sr["resistances"]]
        # Soportes de mayor a menor (primero el más cercano por abajo)
        assert support_levels == sorted(support_levels, reverse=True)
        # Resistencias de menor a mayor (primero la más cercana por arriba)
        assert resistance_levels == sorted(resistance_levels)

    @pytest.mark.unit
    def test_respects_max_levels_and_distance_sign(self):
        df = make_ohlcv_df(drift=0.0)
        sr = calculate_support_resistance(df, max_levels=2)

        assert len(sr["supports"]) <= 2
        assert len(sr["resistances"]) <= 2
        assert all(s["distance_pct"] < 0 for s in sr["supports"])
        assert all(r["distance_pct"] > 0 for r in sr["resistances"])
        assert all(s["touches"] >= 1 for s in sr["supports"])


class TestFibonacci:

    @pytest.mark.unit
    def test_levels_follow_retracement_formula(self):
        df = make_ohlcv_df(drift=0.0)
        fibo = calculate_fibonacci_levels(df, lookback=180)

        high, low = fibo["swing_high"], fibo["swing_low"]
        rng = high - low
        assert rng > 0
        for level in fibo["levels"]:
            if fibo["direction"] == "ALCISTA":
                expected = high - rng * level["ratio"]
            else:
                expected = low + rng * level["ratio"]
            assert level["price"] == pytest.approx(expected, rel=1e-3)
            # Todo retroceso queda dentro del rango del impulso
            assert low <= level["price"] <= high

    @pytest.mark.unit
    def test_upswing_direction_detected(self):
        # Subida sostenida: el máximo es posterior al mínimo → impulso alcista
        df = make_ohlcv_df(drift=0.5, wave=2.0)
        fibo = calculate_fibonacci_levels(df)
        assert fibo["direction"] == "ALCISTA"

    @pytest.mark.unit
    def test_downswing_direction_detected(self):
        df = make_ohlcv_df(start=300.0, drift=-0.5, wave=2.0)
        fibo = calculate_fibonacci_levels(df)
        assert fibo["direction"] == "BAJISTA"

    @pytest.mark.unit
    def test_nearest_level_is_closest_to_price(self):
        df = make_ohlcv_df(drift=0.0)
        fibo = calculate_fibonacci_levels(df)
        last_price = float(df["close"].iloc[-1])

        distances = [abs(l["price"] - last_price) for l in fibo["levels"]]
        assert abs(fibo["nearest_level"]["price"] - last_price) == min(distances)


class TestTrendClassification:

    @pytest.mark.unit
    def test_uptrend_is_alcista(self):
        df = make_ohlcv_df(rows=300, drift=0.5, wave=2.0)
        trend = classify_trend(df)
        assert trend["trend"] == TREND_UP
        assert trend["price_vs_sma_pct"] > 0
        assert trend["ema_slope_pct"] > 0

    @pytest.mark.unit
    def test_downtrend_is_bajista(self):
        df = make_ohlcv_df(rows=300, start=400.0, drift=-0.5, wave=2.0)
        trend = classify_trend(df)
        assert trend["trend"] == TREND_DOWN
        assert trend["price_vs_sma_pct"] < 0
        assert trend["ema_slope_pct"] < 0

    @pytest.mark.unit
    def test_flat_market_is_lateral(self):
        # Onda corta y suave: la EMA50 la filtra casi por completo → pendiente plana
        df = make_ohlcv_df(rows=300, drift=0.0, wave=2.0, period=7)
        trend = classify_trend(df)
        assert trend["trend"] == TREND_SIDEWAYS

    @pytest.mark.unit
    def test_uses_sma200_with_enough_data(self):
        df = make_ohlcv_df(rows=300)
        assert classify_trend(df)["sma_period"] == 200


class TestBuildConfluenceCard:

    @pytest.mark.unit
    def test_card_aggregates_all_sections(self):
        df = make_ohlcv_df(rows=300, drift=0.3)
        card = build_confluence_card(df, "btc")

        for key in (
            "symbol", "last_price", "generated_at", "trend",
            "support_resistance", "fibonacci", "signals", "verdict",
            "narrative", "analysis_paragraphs",
        ):
            assert key in card, f"Falta la clave '{key}' en la card"

        assert card["symbol"] == "BTC"
        assert card["verdict"]["verdict"] in (
            "COMPRA_FUERTE", "COMPRA", "NEUTRAL", "VENTA", "VENTA_FUERTE"
        )
        assert 5 <= card["verdict"]["confidence_pct"] <= 95
        assert card["verdict"]["confidence_level"] in ("ALTA", "MEDIA", "BAJA")
        assert card["signals"]["summary"]["total"] > 5

    @pytest.mark.unit
    def test_narrative_is_spanish_analysis_of_250_to_450_words(self):
        df = make_ohlcv_df(rows=300, drift=0.3)
        card = build_confluence_card(df, "BTC")

        paragraphs = card["analysis_paragraphs"]
        assert len(paragraphs) == 5
        word_count = sum(len(p.split()) for p in paragraphs)
        assert 250 <= word_count <= 450, f"Narrativa de {word_count} palabras"
        # Determinista y derivada de los datos
        full_text = " ".join(paragraphs)
        assert "BTC" in full_text
        assert "USD" in full_text
        assert "asesoramiento financiero" in full_text

    @pytest.mark.unit
    def test_narrative_is_deterministic(self):
        df = make_ohlcv_df(rows=300, drift=0.3)
        first = build_confluence_card(df, "BTC")["analysis_paragraphs"]
        second = build_confluence_card(df, "BTC")["analysis_paragraphs"]
        assert first == second
