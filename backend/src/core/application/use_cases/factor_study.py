"""
factor_study.py — ¿Le queda alfa a esta estrategia después de los factores?

Construye el panel semanal desde el almacén OHLCV propio, levanta los tres
factores de Liu-Tsyvinski-Wu y mide el alfa de una serie de retornos contra
ellos.

Por qué esto cambia lo que el motor puede afirmar
─────────────────────────────────────────────────
Hasta ahora una estrategia del libro se presentaba con su Sharpe fuera de muestra,
deflactado y neto de costes. Todo correcto, y todo insuficiente para la única
pregunta que hace un inversor: **¿esto aporta algo que no pueda comprar más
barato?** Una estrategia con Sharpe 2 que resulta ser beta de mercado apalancada
no tiene nada que vender — el mercado se compra sin pagar comisión de gestión.

LTW midieron nueve estrategias long-short que por separado daban retornos
significativos. Ajustadas por los tres factores, **ninguna** conservaba alfa. Ese
es el listón, y es el que faltaba aquí.

El desplazamiento de las variables de ordenación, que es donde está la fuga
──────────────────────────────────────────────────────────────────────────
El tamaño y el momento con los que se ordena la semana `t` salen de datos hasta
`t−1`. Ordenar con el volumen o el retorno de la propia semana `t` produciría
factores espectaculares y falsos, porque estarían clasificando con lo que se
quiere predecir. Se hace aquí y se declara aquí; el dominio ordena con lo que le
llega y no puede comprobarlo por sí mismo.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from core.domain.services import crypto_factors as cf

logger = logging.getLogger(__name__)

# Velas diarias a pedir por activo. Dos años dan ~104 semanas, que es el orden de
# magnitud mínimo para una regresión de cuatro parámetros con errores robustos.
DEFAULT_DAYS = 730

# Universo: los activos con más capitalización del almacén. La capitalización
# ACTUAL se usa solo para elegir a quién mirar, nunca para ordenar carteras del
# pasado — eso último sí sería lookahead. Elegir el universo con datos de hoy
# introduce sesgo de supervivencia, y se declara en la salida porque no se puede
# eliminar sin un histórico de altas y bajas por activo.
DEFAULT_UNIVERSE = 25


class FactorStudyUseCase:
    """Panel semanal, factores y alfa contra ellos."""

    def execute(self, strategy_returns=None, symbols: list[str] | None = None,
                days: int = DEFAULT_DAYS,
                universe_size: int = DEFAULT_UNIVERSE) -> dict:
        panel, cobertura = self._build_panel(symbols, days, universe_size)
        if panel is None or panel.empty:
            return {"available": False, "coverage": cobertura,
                    "note": ("Sin panel suficiente en el almacén OHLCV: los "
                             "factores no se pueden construir.")}

        construccion = cf.build_factors(panel)
        salida = {
            "coverage": cobertura,
            "factors": {k: v for k, v in construccion.items() if k != "factors"},
        }
        if not construccion["available"]:
            salida["available"] = False
            salida["note"] = construccion["note"]
            return salida

        factores = construccion["factors"]
        salida["available"] = True
        salida["factor_summary"] = self._summarise(factores)

        if strategy_returns is not None:
            salida["alpha"] = cf.factor_alpha(strategy_returns, factores)

        salida["survivorship_warning"] = (
            f"El universo son los {universe_size} activos con más capitalización "
            "HOY. Los que desaparecieron en el tramo no están, así que los factores "
            "están medidos sobre supervivientes y su rendimiento está sesgado al "
            "alza. Corregirlo necesita el histórico de altas y bajas por activo.")
        return salida

    # ------------------------------------------------------------------

    @staticmethod
    def _summarise(factores: pd.DataFrame) -> dict:
        """Media anualizada y estadístico t de cada factor, para poder situarlos."""
        salida = {}
        for nombre in cf.FACTOR_NAMES:
            serie = factores[nombre].to_numpy(dtype=float)
            serie = serie[np.isfinite(serie)]
            if serie.size < 5:
                salida[nombre] = {"periods": int(serie.size)}
                continue
            media = float(serie.mean())
            sd = float(serie.std(ddof=1))
            t = media / (sd / np.sqrt(serie.size)) if sd > 0 else 0.0
            salida[nombre] = {
                "periods": int(serie.size),
                "mean_weekly_pct": round(media * 100, 4),
                "annualized_pct": round(media * cf.PERIODS_PER_YEAR * 100, 2),
                "t_stat": round(float(t), 2),
            }
        return salida

    def _build_panel(self, symbols, days: int, universe_size: int):
        """Panel semanal (periodo, activo, retorno, tamaño, momento)."""
        try:
            from core.application.use_cases.ohlcv_store import load_dataframe
            from core.infrastructure.persistence.models import CryptoAsset
        except Exception:  # noqa: BLE001
            return None, {"available": False, "note": "Persistencia no disponible."}

        if not symbols:
            symbols = list(
                CryptoAsset.objects.exclude(market_cap__isnull=True)
                .order_by("-market_cap").values_list("symbol", flat=True)[:universe_size]
            )
        if not symbols:
            return None, {"available": False,
                          "note": "Sin activos con capitalización en el almacén."}

        trozos, sin_datos = [], []
        for symbol in symbols:
            try:
                df = load_dataframe(symbol, "1d", limit=days)
            except Exception:  # noqa: BLE001 — un activo sin velas no frena el panel
                df = None
            if df is None or len(df) < 60:
                sin_datos.append(symbol)
                continue
            trozos.append(self._weekly(symbol, df))

        if not trozos:
            return None, {"available": False, "symbols_requested": len(symbols),
                          "symbols_without_data": sin_datos,
                          "note": "Ningún activo del universo tiene velas diarias."}

        panel = pd.concat(trozos, ignore_index=True)
        return panel, {
            "available": True,
            "symbols_used": len(trozos),
            "symbols_without_data": sin_datos,
            "days_requested": days,
            "weeks": int(panel["period"].nunique()),
        }

    @staticmethod
    def _weekly(symbol: str, df: pd.DataFrame) -> pd.DataFrame:
        """
        Agrega velas diarias a semanas y construye las columnas de ordenación
        DESPLAZADAS.

        `size` y `mom` llevan `.shift(1)`: describen la semana anterior. Sin ese
        desplazamiento se estaría ordenando la semana `t` con información de `t`,
        y el factor saldría magnífico por construcción.
        """
        d = df.copy()
        if "timestamp" in d.columns:
            d["fecha"] = pd.to_datetime(d["timestamp"], unit="ms", utc=True)
        else:
            d["fecha"] = pd.to_datetime(d.index, utc=True)
        d = d.set_index("fecha").sort_index()

        semanal = pd.DataFrame({
            "close": d["close"].resample("W").last(),
            "dollar_volume": (d["volume"] * d["close"]).resample("W").sum(),
        }).dropna()

        semanal["ret"] = semanal["close"].pct_change()
        # Momento: retorno acumulado de las semanas previas, ya desplazado.
        semanal["mom"] = (semanal["close"].pct_change(cf.MOMENTUM_LOOKBACK_WEEKS)
                          .shift(1))
        semanal["size"] = semanal["dollar_volume"].shift(1)

        salida = semanal.dropna(subset=["ret", "mom", "size"]).reset_index()
        salida["symbol"] = symbol
        salida["period"] = salida["fecha"].dt.strftime("%Y-%W")
        return salida[["period", "symbol", "ret", "size", "mom"]]
