"""
carry_test.py — El carry sobre el funding real de un activo.

Es el equivalente de `edge_test` para la otra mitad del documento: no decide qué
pregunta tiene señal, decide si un flujo de caja contractual sobrevive a sus
costes. Y como aquel, existe para poder decir que NO.

De dónde sale el histórico
──────────────────────────
Del almacén propio (`FundingRateRecord`) y, si está vacío o corto, del endpoint
histórico de Binance a través del backfill que ya existe. Esto importa más de lo
que parece: significa que el carry **no depende de que la tarea de archivado
haya estado corriendo**. El funding se puede reconstruir hacia atrás bajo
demanda, así que el veredicto se puede emitir el primer día.

Lo que no se puede reconstruir hacia atrás es la profundidad del libro, y por eso
el coste de ejecución que entra aquí es el del modelo y no el medido. Queda
declarado en la salida.
"""

from __future__ import annotations

import logging

from core.domain.services import carry as c

logger = logging.getLogger(__name__)

# Tamaño por defecto del estudio. Modesto a propósito: la ventaja estructural de
# operar capital pequeño es precisamente poder entrar donde un fondo no entra, y
# un estudio dimensionado a 10 millones respondería a otra pregunta.
DEFAULT_NOTIONAL_USD = 10_000.0

# Shock de referencia para la prueba de margen. Un 15 % en un día es grande pero
# no excepcional en cripto: ha ocurrido varias veces en cada uno de los últimos
# años, así que es el escenario correcto para decidir apalancamiento.
DEFAULT_SHOCK_PCT = 15.0


class CarryTestUseCase:
    """¿Sobrevive el carry de este activo a sus costes y a un shock?"""

    def execute(self, asset_symbol: str, notional_usd: float = DEFAULT_NOTIONAL_USD,
                margin_pct: float = 0.20, shock_pct: float = DEFAULT_SHOCK_PCT,
                taker_fee_bps: float = 5.0, slippage_bps: float = 2.0,
                capital_cost_annual_pct: float = 0.0,
                days: int = 365) -> dict:
        symbol = asset_symbol.upper()
        rates, cobertura = self._load_funding(symbol, days)
        if not rates:
            return {
                "symbol": symbol,
                "verdict": "SIN_DATOS",
                "tradeable": False,
                "note": (f"Sin histórico de financiación para {symbol}. Se puede "
                         "traer con el backfill de funding; sin él no hay nada "
                         "que medir."),
                "funding_coverage": cobertura,
            }

        position = c.CarryPosition(notional_usd=notional_usd, margin_pct=margin_pct)
        costs = c.CarryCosts(taker_fee_bps=taker_fee_bps, slippage_bps=slippage_bps,
                             capital_cost_annual_pct=capital_cost_annual_pct)

        # La cadencia sale del dato, no de una constante. Con 1.095 clavado, un
        # símbolo horario contaba 45 días como un año y el rendimiento anualizado
        # salía dividido por ocho.
        ppy = (c.periods_per_year(cobertura["interval_hours"])
               if cobertura.get("interval_hours") else c.DEFAULT_PERIODS_PER_YEAR)
        observed = c.simulate_carry(rates, position, costs, periods_per_year_=ppy)
        null = c.null_distribution(rates, position, costs, periods_per_year_=ppy)
        shock = c.shock_margin_probability(rates, position, shock_pct)
        verdict = c.carry_verdict(observed, null, shock)

        report = {
            "symbol": symbol,
            "notional_usd": notional_usd,
            "margin_pct": margin_pct,
            "observed": observed,
            "null": null,
            "shock": shock,
            "funding_coverage": cobertura,
            "protocol": (
                "Tres condiciones, todas necesarias: cubrir las CUATRO comisiones "
                "(dos patas, entrada y salida), superar el percentil 95 de un "
                "funding sin sesgo de signo, y sobrevivir al shock declarado. El "
                "nulo aleatoriza el signo conservando la magnitud: destruye solo "
                "la afirmación bajo prueba —que el funding es sistemáticamente "
                "positivo— y no la escala ni la volatilidad."),
        }
        report.update(verdict)
        logger.info("carry_test %s → %s", symbol, report["verdict"])
        return report

    # ------------------------------------------------------------------

    def _load_funding(self, symbol: str, days: int) -> tuple[list[float], dict]:
        """Tasas del almacén propio, con su cobertura declarada.

        `funding_time` se guarda como epoch en milisegundos, no como fecha, así
        que el corte temporal se hace en esa misma unidad. Pasar un `datetime` a
        un `BigIntegerField` no falla de forma visible en todos los backends —
        compara mal y devuelve de menos— y un tramo recortado en silencio daría
        un veredicto sobre menos historia de la que hay.
        """
        try:
            from datetime import datetime, timedelta, timezone as _tz

            from core.infrastructure.persistence.models import FundingRateRecord

            desde_ms = int((datetime.now(_tz.utc) - timedelta(days=days)).timestamp() * 1000)
            qs = (FundingRateRecord.objects
                  .filter(symbol=self._pair(symbol), funding_time__gte=desde_ms)
                  .order_by("funding_time")
                  .values_list("funding_rate", "funding_time"))
            filas = list(qs)
        except Exception:  # noqa: BLE001 — sin almacén el estudio lo dice, no revienta
            logger.info("carry_test: almacén de funding no disponible para %s", symbol)
            return [], {"available": False,
                        "note": "Almacén de financiación no disponible."}

        if not filas:
            return [], {"available": False, "periods": 0,
                        "note": (f"No hay financiación archivada para {symbol} en los "
                                 f"últimos {days} días.")}

        def _iso(ms: int) -> str:
            from datetime import datetime, timezone as _tz
            return datetime.fromtimestamp(int(ms) / 1000, _tz.utc).isoformat()

        rates = [float(r) for r, _ in filas]
        # Cadencia REAL, derivada de las marcas temporales: la mediana de los
        # huecos entre liquidaciones. Se usa la mediana y no la media porque un
        # hueco de recogida —un día que el recolector no corrió— desplazaría la
        # media y con ella el rendimiento anualizado.
        cadencia_horas = None
        if len(filas) >= 3:
            import numpy as _np
            marcas = _np.array([int(t) for _, t in filas], dtype=float)
            huecos = _np.diff(marcas) / 3_600_000.0
            huecos = huecos[huecos > 0]
            if huecos.size:
                cadencia_horas = float(_np.median(huecos))

        return rates, {
            "available": True,
            "periods": len(rates),
            "interval_hours": round(cadencia_horas, 3) if cadencia_horas else None,
            "first": _iso(filas[0][1]),
            "last": _iso(filas[-1][1]),
            "days_requested": days,
            "note": (
                f"{len(rates)} liquidaciones archivadas"
                + (f" con cadencia mediana de {cadencia_horas:.1f} h, así que un "
                   f"año completo son {c.periods_per_year(cadencia_horas):.0f}."
                   if cadencia_horas else
                   ". Cadencia no derivable con tan pocas marcas: se usa la de 8 h.")
            ),
        }

    @staticmethod
    def _pair(symbol: str) -> str:
        """Símbolo del perpetuo USDⓈ-M, como lo guarda el almacén."""
        s = symbol.upper()
        return s if s.endswith("USDT") else f"{s}USDT"
