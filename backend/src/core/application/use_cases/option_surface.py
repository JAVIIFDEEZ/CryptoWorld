"""
option_surface.py — La superficie de opciones convertida en métricas, y archivada.

Une las tres piezas: el adaptador de Deribit trae la cadena, el dominio
(`option_moments`) calcula los momentos, y el almacén genérico de derivados
(`DerivativeMetricPoint`) los guarda con sello point-in-time.

Por qué el archivado no es opcional aquí
────────────────────────────────────────
El factor con más contenido predictivo que reporta la literatura sobre opciones
de cripto es la **volatilidad de la volatilidad**: la variabilidad de la varianza
implícita a lo largo del tiempo. Eso no sale de una foto — necesita serie.

Una cadena de opciones no se puede reconstruir hacia atrás: Deribit no publica el
histórico de la superficie, así que cada ejecución que no ocurre es un punto que
no existirá nunca. Es la misma asimetría que la profundidad del libro, y por el
mismo motivo esto pertenece a una tarea programada y no a un comando manual.

El delta es lo único que NO es libre de modelo
──────────────────────────────────────────────
La varianza implícita se calcula sin suponer ningún modelo de precios. Pero
localizar «la put de 25 delta» sí requiere uno: el delta no se observa, se
calcula. Aquí se usa Black-76 sobre la volatilidad implícita de marca, y queda
declarado en la salida — es exactamente el tipo de detalle que convierte una
cifra auditable en una que parece un dato.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone as _tz

import numpy as np

from core.domain.services import option_moments as om

logger = logging.getLogger(__name__)

# Vencimiento objetivo, en días. Treinta es la convención del VIX y el horizonte
# en el que la literatura de cripto reporta los resultados. Se elige el
# vencimiento cotizado más cercano a esta cifra en vez de interpolar entre dos:
# interpolar la superficie añade un supuesto más y el beneficio es marginal
# cuando lo que se persigue es una serie, no un índice publicable.
TARGET_DAYS = 30.0

# Días mínimos al vencimiento. Por debajo, la volatilidad implícita se vuelve
# errática —el gamma explota y el precio lo domina el intrínseco— y ensucia la
# serie más de lo que informa.
MIN_DAYS = 5.0

# Nombres de métrica en el almacén. Se fijan como constantes por el mismo motivo
# que las de derivados: son la clave con la que se leerán dentro de meses.
IV_30D = "option_iv_30d"
RR_25D = "option_rr_25d"
BF_25D = "option_bf_25d"
OPTION_METRICS = (IV_30D, RR_25D, BF_25D)


def _black76_delta(forward: float, strike: float, iv: float, T: float,
                   is_call: bool) -> float | None:
    """Delta de Black-76. El único número de todo esto que supone un modelo."""
    if forward <= 0 or strike <= 0 or iv <= 0 or T <= 0:
        return None
    from scipy.stats import norm

    sq = iv * np.sqrt(T)
    d1 = (np.log(forward / strike) + 0.5 * sq ** 2) / sq
    return float(norm.cdf(d1)) if is_call else float(-norm.cdf(-d1))


class OptionSurfaceUseCase:
    """Momentos implícitos del vencimiento más cercano a 30 días."""

    def execute(self, currency: str = "BTC", client=None,
                realized_vol_annual: float | None = None,
                persist: bool = True) -> dict:
        from core.infrastructure.external_apis.deribit_client import (
            DeribitPublicClient, parse_instrument,
        )

        moneda = currency.upper()
        cliente = client or DeribitPublicClient()
        try:
            filas = cliente.option_book_summary(moneda)
        except Exception as exc:  # noqa: BLE001 — una fuente caída no revienta
            logger.info("option_surface: Deribit no disponible (%s)", type(exc).__name__)
            return {"available": False, "currency": moneda,
                    "note": f"Deribit no disponible ({type(exc).__name__})."}

        ahora = datetime.now(_tz.utc)
        por_vencimiento: dict[datetime, list] = {}
        subyacente = None

        for fila in filas or []:
            info = parse_instrument(fila.get("instrument_name", ""))
            if info is None or info["currency"] != moneda:
                continue
            dias = (info["expiry"] - ahora).total_seconds() / 86_400.0
            if dias < MIN_DAYS:
                continue
            iv = fila.get("mark_iv")
            precio = fila.get("mark_price")
            sub = fila.get("underlying_price") or fila.get("estimated_delivery_price")
            if iv is None or precio is None or sub is None:
                continue
            if sub:
                subyacente = float(sub)
            por_vencimiento.setdefault(info["expiry"], []).append({
                # mark_iv viene en PORCENTAJE y mark_price en unidades del
                # subyacente: las dos conversiones, aquí y no en el dominio.
                "strike": info["strike"], "is_call": info["is_call"],
                "iv": float(iv) / 100.0, "price_usd": float(precio) * float(sub),
                "days": dias,
            })

        if not por_vencimiento or subyacente is None:
            return {"available": False, "currency": moneda,
                    "note": ("La cadena llegó vacía o sin precio de subyacente "
                             f"utilizable para {moneda}.")}

        # Vencimiento cotizado más cercano a 30 días.
        elegido = min(por_vencimiento,
                      key=lambda e: abs((e - ahora).total_seconds() / 86_400.0
                                        - TARGET_DAYS))
        patas = por_vencimiento[elegido]
        dias = float(np.mean([p["days"] for p in patas]))
        T = dias / om.DAYS_PER_YEAR

        quotes = self._to_quotes(patas, subyacente, T)
        varianza = om.model_free_variance(quotes, subyacente, dias)
        alas = om.wing_structure(quotes)

        salida = {
            "available": bool(varianza.get("available")),
            "currency": moneda,
            "underlying_price": round(subyacente, 2),
            "expiry": elegido.isoformat(),
            "days_to_expiry": round(dias, 2),
            "expiries_available": len(por_vencimiento),
            "variance": varianza,
            "wings": alas,
            "delta_model": "BLACK76",
            "note": (
                "La varianza implícita es LIBRE DE MODELO. El delta con el que se "
                "localizan las alas de 25 no lo es: no se observa, se calcula con "
                "Black-76 sobre la volatilidad de marca."),
        }

        if realized_vol_annual is not None and varianza.get("available"):
            salida["vrp"] = om.variance_risk_premium(
                varianza["variance_annual"], float(realized_vol_annual) ** 2)

        if persist and salida["available"]:
            salida["stored"] = self._persist(moneda, varianza, alas)
        return salida

    # ------------------------------------------------------------------

    @staticmethod
    def _to_quotes(patas: list[dict], forward: float, T: float) -> list[om.OptionQuote]:
        """Agrupa las dos patas de cada strike y calcula sus deltas."""
        por_strike: dict[float, dict] = {}
        for p in patas:
            entrada = por_strike.setdefault(p["strike"], {})
            entrada["call" if p["is_call"] else "put"] = p

        quotes = []
        for strike, lados in sorted(por_strike.items()):
            call, put = lados.get("call"), lados.get("put")
            quotes.append(om.OptionQuote(
                strike=strike,
                call_price=call["price_usd"] if call else None,
                put_price=put["price_usd"] if put else None,
                call_iv=call["iv"] if call else None,
                put_iv=put["iv"] if put else None,
                call_delta=(_black76_delta(forward, strike, call["iv"], T, True)
                            if call else None),
                put_delta=(_black76_delta(forward, strike, put["iv"], T, False)
                           if put else None),
            ))
        return quotes

    @staticmethod
    def _persist(currency: str, varianza: dict, alas: dict) -> int:
        """
        Guarda los momentos como serie, con sello point-in-time.

        Reutiliza el almacén genérico de derivados: son series escalares por
        (activo, venue, métrica, instante), que es exactamente lo que son estas.
        Sin esto, la volatilidad de la volatilidad nunca será calculable.
        """
        from core.infrastructure.persistence.models import DerivativeMetricPoint

        ahora_ms = int(datetime.now(_tz.utc).timestamp() * 1000)
        puntos = [(IV_30D, varianza.get("implied_vol_annual"))]
        if alas.get("available"):
            puntos.append((RR_25D, alas.get("risk_reversal_pct")))
            if alas.get("butterfly_pct") is not None:
                puntos.append((BF_25D, alas.get("butterfly_pct")))

        filas = [
            DerivativeMetricPoint(symbol=currency, venue="deribit", metric=m,
                                  observed_at=ahora_ms, value=float(v))
            for m, v in puntos if v is not None
        ]
        if not filas:
            return 0
        base = DerivativeMetricPoint.objects.filter(symbol=currency, venue="deribit")
        antes = base.count()
        DerivativeMetricPoint.objects.bulk_create(filas, ignore_conflicts=True)
        return max(base.count() - antes, 0)


def vol_of_vol(currency: str = "BTC", days: int = 30) -> dict:
    """
    Volatilidad de la volatilidad: la desviación de la varianza implícita.

    Es el factor que la literatura señala como el de mayor contenido predictivo
    sobre el exceso de retorno de BTC, y el único de este módulo que NO sale de
    una foto: necesita serie. Se calcula sobre lo archivado.

    Mientras no haya suficientes puntos, devuelve por qué no — que es distinto de
    devolver cero.
    """
    from core.infrastructure.persistence.models import DerivativeMetricPoint

    desde = int((datetime.now(_tz.utc).timestamp() - days * 86_400) * 1000)
    valores = list(DerivativeMetricPoint.objects
                   .filter(symbol=currency.upper(), venue="deribit", metric=IV_30D,
                           observed_at__gte=desde)
                   .order_by("observed_at").values_list("value", flat=True))

    if len(valores) < 10:
        return {
            "available": False,
            "points": len(valores),
            "note": (f"Solo {len(valores)} lecturas archivadas de volatilidad "
                     "implícita. La volatilidad de la volatilidad necesita serie y "
                     "una cadena de opciones no se puede reconstruir hacia atrás: "
                     "hay que esperar a que el recolector acumule."),
        }

    arr = np.asarray(valores, dtype=float)
    cambios = np.diff(arr)
    return {
        "available": True,
        "points": int(arr.size),
        "days": days,
        "iv_mean_pct": round(float(arr.mean()) * 100, 2),
        "vov": round(float(np.std(cambios, ddof=1)), 6),
        "vov_pct_of_iv": round(float(np.std(cambios, ddof=1) / arr.mean()) * 100, 2)
        if arr.mean() > 0 else None,
        "note": ("Desviación típica de los cambios de la volatilidad implícita a 30 "
                 "días. Se mide sobre CAMBIOS y no sobre niveles: la desviación del "
                 "nivel mezcla el régimen de volatilidad con su inestabilidad, que "
                 "son cosas distintas."),
    }
