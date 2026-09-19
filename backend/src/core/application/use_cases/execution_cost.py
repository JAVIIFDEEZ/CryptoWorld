"""
execution_cost.py — ¿Qué cuesta actuar sobre esta señal, a MI tamaño?

Por qué existe este caso de uso
───────────────────────────────
Todo lo que esta plataforma muestra —un veredicto de dirección, una estrategia
del libro, una alerta de confluencia— es **inaccionable** mientras no se sepa
qué cuesta tomarlo. Un edge de 30 puntos básicos es un negocio a 10.000 USD y
una pérdida a 1.000.000 en un activo estrecho, y es el mismo edge: lo que cambia
es el coste de ejecutarlo.

Es además la pieza que separa un panel de análisis de una herramienta de
decisión, y ninguno de los competidores del segmento la enseña: el dato de
profundidad se vende como producto de datos —Kaiko y equivalentes— y los
terminales retail muestran el precio sin decir a qué tamaño sigue siendo válido.

Qué usa, y por qué basta
────────────────────────
Volumen medio diario en USD y volatilidad diaria, ambos del almacén OHLCV que ya
existe. No hace falta nada nuevo para responder la pregunta con un modelo, y
ese es justamente el motivo de construir esto antes que la ingesta de
profundidad: se puede entregar hoy y se puede validar el día que haya libro.

Lo que NO es
────────────
No es una lectura del libro de órdenes. La plataforma consulta profundidad en
vivo pero no la archiva, así que no hay serie con la que calcular el coste real
hacia atrás ni con la que contrastar este modelo. La salida lo declara en cada
respuesta (`method`, `note`) en lugar de dejar que «12 bps» se lea como una
medición. Cuando exista esa serie, este mismo caso de uso es el sitio donde el
modelo se comparará contra el coste observado.
"""

from __future__ import annotations

import logging

from core.domain.services import market_impact as mi

logger = logging.getLogger(__name__)

# Ventana de calibración, en días. Treinta días de volumen y volatilidad son el
# compromiso habitual: suficientes para que un día raro no domine la media, y
# pocos como para que el régimen actual siga siendo el que se está midiendo.
DEFAULT_WINDOW_DAYS = 30

# Velas diarias a pedir. Una más que la ventana, porque la volatilidad se
# calcula sobre retornos y un retorno consume dos cierres.
_CANDLES = DEFAULT_WINDOW_DAYS + 5


class ExecutionCostUseCase:
    """Escalera de coste de ejecución por tamaño, para un activo."""

    def execute(self, asset_symbol: str, notionals: tuple | None = None,
                window_days: int = DEFAULT_WINDOW_DAYS) -> dict:
        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe

        symbol = asset_symbol.upper()
        result = fetch_ohlcv_dataframe(symbol=symbol, interval="1d", limit=_CANDLES)
        if result is None or result.df is None or len(result.df) < 5:
            return {
                "symbol": symbol,
                "available": False,
                "steps": [],
                "note": (f"Sin histórico diario suficiente para {symbol}: el coste "
                         "de ejecución no se puede estimar."),
            }

        df = result.df
        adv = mi.average_daily_volume_usd(df, window=window_days)
        vol = mi.daily_volatility_of(df, window=window_days)
        ladder = mi.cost_ladder(adv, vol, notionals or mi.DEFAULT_LADDER)

        ladder["symbol"] = symbol
        ladder["window_days"] = int(window_days)
        ladder["candles"] = int(len(df))
        ladder["data_source"] = result.source
        return ladder
