"""
ohlcv_health.py — Caso de uso: observabilidad de la salud del almacén OHLCV.

Recorre las series (símbolo+marco) presentes en el almacén propio, reutiliza la
cobertura y detección de huecos existentes y puntúa cada una con el dominio de
calidad de datos. Devuelve el detalle por serie + un resumen global.
"""

from __future__ import annotations

import logging

from core.domain.services.data_quality import series_health, overall_health

logger = logging.getLogger(__name__)


class OhlcvHealthUseCase:
    """Salud del almacén histórico OHLCV: completitud, frescura y huecos."""

    _MAX_SERIES = 60   # tope defensivo de series a evaluar

    def execute(self) -> dict:
        from django.db.models import Count
        from core.infrastructure.persistence.models import OhlcvCandle
        from core.application.use_cases.ohlcv_store import coverage, _INTERVAL_MS, _now_ms

        combos = list(
            OhlcvCandle.objects.values("symbol", "interval")
            .annotate(n=Count("id")).order_by("-n")[:self._MAX_SERIES]
        )
        if not combos:
            return {"status": "EMPTY", "series": [],
                    "summary": overall_health([]),
                    "note": "El almacén OHLCV aún no tiene datos."}

        now_ms = _now_ms()
        rows = []
        for c in combos:
            symbol, interval = c["symbol"], c["interval"]
            cov = coverage(symbol, interval)
            health = series_health(
                candles=cov["candles"], missing_candles=cov["missing_candles"],
                last_ms=cov["last"], now_ms=now_ms,
                step_ms=_INTERVAL_MS.get(interval),
            )
            rows.append({
                "symbol": symbol, "interval": interval,
                "candles": cov["candles"], "gaps": cov["gaps"],
                "missing_candles": cov["missing_candles"],
                "first": cov["first"], "last": cov["last"],
                **health,
            })

        # Peores primero: desactualizados/huecos arriba, luego por completitud.
        _RANK = {"VACIO": 0, "DESACTUALIZADO": 1, "CON_HUECOS": 2, "SANO": 3}
        rows.sort(key=lambda r: (_RANK.get(r["status"], 9), r["completeness_pct"]))

        return {
            "status": "OK",
            "series": rows,
            "summary": overall_health(rows),
            "universe": self._universe_health(),
            "note": (
                "Salud del almacén histórico OHLCV propio: completitud (velas "
                "presentes vs esperadas), frescura (antigüedad de la última "
                "vela) y huecos, por serie. Alimenta la fiabilidad de todo lo "
                "que se deriva del histórico (riesgo, backtests, terminal)."
            ),
        }

    @staticmethod
    def _universe_health() -> dict:
        """
        Sesgo de supervivencia: ¿se puede reconstruir el universo tal como era,
        o solo la lista de los que llegaron vivos hasta hoy?

        Va en el informe de salud de datos y no en un rincón porque es un
        problema DE DATOS, no de método: ninguna corrección estadística arregla
        un histórico al que le faltan los muertos. Y a diferencia del ruido,
        este error tiene dirección fija — siempre infla el rendimiento.
        """
        from core.domain.services import universe
        from core.infrastructure.persistence.models import CryptoAsset

        assets = universe.from_records(
            CryptoAsset.objects.values("symbol", "listed_at", "delisted_at",
                                       "delisting_reason")
        )
        return universe.coverage(assets)
