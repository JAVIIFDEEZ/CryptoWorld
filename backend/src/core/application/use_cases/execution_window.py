"""
execution_window.py — La ventana de ejecución de un activo, sobre datos propios.

Compone tres cosas que ya existían por separado y que nunca se habían mirado
juntas: la rejilla de hora de la semana, el calendario de eventos derivables y el
coste de ejecución a tamaño. El resultado responde a la pregunta que decide cuánto
del edge llega a la cuenta — **¿ejecuto ahora o espero?** — y es la mitad del
problema que el resto del motor no toca.

Dos decisiones de implementación que importan
─────────────────────────────────────────────
· **La rejilla se calcula con pocas réplicas y se cachea arriba.** El estudio de
  estacionalidad con 500 réplicas tarda segundos, y esto se consulta desde una
  pantalla. Se baja a `SEASONALITY_ROTATIONS` y la vista lo cachea: el contraste
  global pierde algo de resolución en la cola, pero el umbral que tiene que cruzar
  es 0,0125 y con 150 réplicas el mínimo alcanzable es 0,0066, así que sigue
  pudiendo pasar. Queda declarado en la salida.
· **El coste puede fallar sin tumbar el resto.** Sale de `fetch_ohlcv_dataframe`,
  que consulta la red si el almacén no llega; en un entorno sin salida eso es una
  excepción. El veredicto horario no depende de él, así que se captura y se
  informa de su ausencia en lugar de dejar la pantalla en blanco.
"""

from __future__ import annotations

import logging
import time

import numpy as np

from core.domain.services import economic_calendar as cal
from core.domain.services import execution_window as ew

logger = logging.getLogger(__name__)

# Velas que se leen para estimar la rejilla. 20.000 horarias son ~2,3 años: con
# menos de 12 observaciones por casilla el estudio se niega a emitir veredicto.
DEFAULT_LIMIT = 20_000

# Réplicas del nulo de la rejilla. Menos que el valor por defecto del dominio
# porque esto se consulta desde una pantalla; el efecto está declarado arriba.
SEASONALITY_ROTATIONS = 150

# Nocional por defecto del estudio de coste.
DEFAULT_NOTIONAL_USD = 10_000.0


class ExecutionWindowUseCase:
    """¿Es buen momento para ejecutar en este activo, y si no, cuándo lo será?"""

    def execute(self, asset_symbol: str, interval: str = "1h",
                notional_usd: float = DEFAULT_NOTIONAL_USD,
                limit: int = DEFAULT_LIMIT,
                horizon_hours: int = ew.DEFAULT_HORIZON_HOURS,
                window_hours: int = ew.DEFAULT_WINDOW_HOURS,
                now_ms: int | None = None) -> dict:
        symbol = asset_symbol.upper()
        ahora = int(now_ms) if now_ms else int(time.time() * 1000)

        marcas, retornos = self._load(symbol, interval, limit)
        if marcas is None:
            return {
                "symbol": symbol, "interval": interval, "verdict": "SIN_DATOS",
                "notional_usd": notional_usd,
                "note": (f"No hay velas archivadas de {symbol} en {interval}. La "
                         f"ventana de ejecución se calcula sobre el almacén propio, "
                         f"así que primero hay que ingerir histórico."),
                "limits": ew.self_note(),
            }

        from core.domain.services import seasonality as sn
        rejilla = sn.analyse(marcas, retornos, rotations=SEASONALITY_ROTATIONS)

        # El calendario cubre el horizonte más un margen, para que la ventana de
        # contagio de un evento justo posterior al horizonte también cuente.
        eventos = cal.derived_calendar(
            ahora - 2 * ew.HORA_MS,
            ahora + (int(horizon_hours) + 4) * ew.HORA_MS,
        )

        coste = self._cost(symbol, notional_usd)
        informe = ew.assess(ahora, rejilla, eventos, coste,
                            horizon_hours=horizon_hours, window_hours=window_hours)

        informe.update({
            "symbol": symbol,
            "interval": interval,
            "notional_usd": float(notional_usd),
            "candles": int(marcas.size),
            "seasonality": {
                "verdict": rejilla.get("verdict"),
                "rotations": rejilla.get("rotations"),
                "cells_significant": rejilla.get("cells_significant", 0),
                "global": rejilla.get("global"),
                "mean_abs_return": rejilla.get("mean_abs_return"),
                "per_cell": rejilla.get("per_cell"),
                "note": rejilla.get("note"),
            },
            "cost": coste,
            "calendar_underivable": sorted(cal.UNDERIVABLE),
        })
        logger.info("execution_window %s %s → %s", symbol, interval,
                    informe["verdict"])
        return informe

    # ------------------------------------------------------------------

    @staticmethod
    def _load(symbol: str, interval: str, limit: int):
        try:
            from core.application.use_cases.ohlcv_store import load_dataframe
            df = load_dataframe(symbol, interval, limit)
        except Exception:  # noqa: BLE001 — sin almacén se dice, no se revienta
            logger.info("execution_window: almacén no disponible para %s", symbol)
            return None, None
        if df is None or len(df) < 3:
            return None, None

        marcas = np.asarray(df["timestamp"].tolist(), dtype=np.int64)
        cierres = np.asarray(df["close"].tolist(), dtype=float)
        cierres = np.where(cierres > 0, cierres, np.nan)
        retornos = np.nan_to_num(np.diff(np.log(cierres)), nan=0.0,
                                 posinf=0.0, neginf=0.0)
        # El retorno `t` se conoce al cerrar la vela `t+1`, así que va con su marca.
        return marcas[1:], retornos

    @staticmethod
    def _cost(symbol: str, notional_usd: float) -> dict | None:
        """Coste de ejecución al tamaño pedido, o `None` si no se puede estimar.

        Se aísla en su propio try porque sale de la cadena que consulta la red: sin
        salida a internet esto lanza, y el veredicto horario —que es el valor
        principal de la pantalla— no depende de él.
        """
        try:
            from core.application.use_cases.execution_cost import ExecutionCostUseCase
            return ExecutionCostUseCase().execute(
                asset_symbol=symbol, notionals=(float(notional_usd),))
        except Exception:  # noqa: BLE001
            logger.info("execution_window: coste no estimable para %s", symbol)
            return None
