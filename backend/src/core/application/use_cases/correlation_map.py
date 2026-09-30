"""
correlation_map.py — El mapa de correlaciones de una cesta, sobre datos propios.

Alimenta el mapa de calor de la interfaz. Corre sobre el almacén propio de velas,
así que no pide nada a ningún exchange.

Lo que este caso de uso añade sobre el dominio
─────────────────────────────────────────────
Una sola cosa, y es la que rompe con datos de verdad: **las series se UNEN por
marca temporal**. `load_dataframe` devuelve las últimas N velas de cada símbolo
por separado, y en este almacén faltan velas —hay un `find_gaps` porque faltan—.
Emparejar por posición dos series con huecos distintos desfasa una respecto a la
otra, y una correlación sobre series desfasadas una barra no es una correlación
mal estimada: es otra cantidad. El informe declara cuántas velas sobrevivieron a
la unión.
"""

from __future__ import annotations

import logging

import numpy as np

from core.domain.services import correlation_heatmap as ch

logger = logging.getLogger(__name__)

# Velas que se piden por símbolo.
DEFAULT_LIMIT = 1200

# Activos por defecto de la cesta, por capitalización.
DEFAULT_TOP = 12


class CorrelationMapUseCase:
    """Matriz de correlaciones ordenada por conglomerados, con su error y su cambio."""

    def execute(self, symbols: list[str] | None = None, interval: str = "1h",
                limit: int = DEFAULT_LIMIT, window: int = ch.DEFAULT_WINDOW,
                reference_window: int | None = None, top: int = DEFAULT_TOP) -> dict:
        elegidos = ([s.upper() for s in dict.fromkeys(symbols)] if symbols
                    else self._top_by_market_cap(top))
        if len(elegidos) < ch.MIN_ASSETS:
            return {"verdict": "SIN_DATOS", "labels": [], "matrix": [],
                    "interval": interval,
                    "note": (f"Hacen falta al menos {ch.MIN_ASSETS} activos y hay "
                             f"{len(elegidos)}.")}

        marcas, retornos, ausentes = self._load_aligned(elegidos, interval, limit)
        if marcas is None:
            return {"verdict": "SIN_DATOS", "labels": [], "matrix": [],
                    "interval": interval, "missing": ausentes,
                    "note": (f"No hay dos activos con histórico alineado en el "
                             f"almacén para {interval}. Faltan: "
                             f"{', '.join(ausentes) or 'ninguno'}.")}

        salida = ch.heatmap(retornos, window=window,
                            reference_window=reference_window)
        salida.update({
            "interval": interval,
            "missing": ausentes,
            "candles_aligned": int(marcas.size),
            "first": self._iso(marcas[0]),
            "last": self._iso(marcas[-1]),
            "limits": ch.self_note(),
        })
        logger.info("correlation_map %s → %s (%d activos)", interval,
                    salida.get("verdict"), len(salida.get("labels") or []))
        return salida

    # ------------------------------------------------------------------

    @staticmethod
    def _top_by_market_cap(top: int) -> list[str]:
        try:
            from core.infrastructure.persistence.models import CryptoAsset
            return list(
                CryptoAsset.objects.exclude(market_cap__isnull=True)
                .order_by("-market_cap").values_list("symbol", flat=True)[:max(top, 0)]
            )
        except Exception:  # noqa: BLE001
            logger.info("correlation_map: no se pudo leer la cesta por capitalización")
            return []

    @staticmethod
    def _load_aligned(simbolos: list[str], interval: str, limit: int):
        """Cierres de todos los símbolos UNIDOS por `open_time`."""
        try:
            from core.application.use_cases.ohlcv_store import load_dataframe
        except Exception:  # noqa: BLE001
            return None, None, list(simbolos)

        cierres: dict[str, dict[int, float]] = {}
        ausentes: list[str] = []
        for s in simbolos:
            try:
                df = load_dataframe(s, interval, limit)
            except Exception:  # noqa: BLE001
                ausentes.append(s)
                continue
            if df is None or len(df) < 2:
                ausentes.append(s)
                continue
            cierres[s] = dict(zip(df["timestamp"].tolist(), df["close"].tolist()))

        if len(cierres) < ch.MIN_ASSETS:
            return None, None, ausentes

        comunes = set.intersection(*(set(v) for v in cierres.values()))
        marcas = np.array(sorted(comunes), dtype=np.int64)
        if marcas.size < 3:
            return None, None, ausentes

        retornos = {}
        for s, serie in cierres.items():
            c = np.array([serie[t] for t in marcas], dtype=float)
            c = np.where(c > 0, c, np.nan)
            retornos[s] = np.nan_to_num(np.diff(np.log(c)), nan=0.0,
                                        posinf=0.0, neginf=0.0)
        # El retorno `t` nace de las velas `t` y `t+1`: se queda con la marca de la
        # segunda, que es cuando se conoce.
        return marcas[1:], retornos, ausentes

    @staticmethod
    def _iso(ms) -> str:
        from datetime import datetime, timezone as _tz
        return datetime.fromtimestamp(int(ms) / 1000, _tz.utc).isoformat()
