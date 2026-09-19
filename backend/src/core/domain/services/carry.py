"""
carry.py — Cosecha de financiación delta-neutral: el flujo que no predice nada.

El mecanismo
────────────
En un perpetuo, cada ocho horas un lado paga al otro por diseño del contrato.
Históricamente el funding es positivo la mayor parte del tiempo porque el retail
está estructuralmente largo. Una posición **delta-neutral** —spot largo más
perpetuo corto del mismo tamaño— cobra ese flujo sin acertar ninguna dirección:
lo que gane una pata lo pierde la otra, y lo que queda es el funding.

Por qué esto es distinto de todo lo demás de este motor
───────────────────────────────────────────────────────
El resto de la plataforma intenta **predecir**, y por eso todo lo gobierna la
misma pregunta: ¿se distingue este resultado del azar? Aquí no hay predicción que
validar. El funding no es un pronóstico, es un flujo de caja contractual: se
cobra o no se cobra, y está en el histórico.

Eso cambia dónde está el riesgo, y conviene decirlo antes de enseñar un número:

  · **No** es riesgo de equivocarse de dirección. La posición es neutral.
  · **Sí** es riesgo de que los costes se coman el flujo. Cuatro comisiones
    —entrada y salida de dos patas— más deslizamiento pueden costar más que
    meses de funding en un régimen tranquilo.
  · **Sí** es riesgo de liquidación de la pata corta. Si el precio sube lo
    suficiente, el margen del perpetuo se agota. La pata de spot sigue ahí y
    sigue valiendo, pero el corto ya se ha cerrado al peor precio posible y la
    neutralidad se ha roto en el peor momento.
  · **Sí** es riesgo de que el funding se vuelva negativo y se quede así. El
    flujo cambia de sentido y pasa a pagarse en vez de cobrarse.

Ninguno de esos cuatro se mide con un contraste de significancia sobre
predicciones. Se miden simulando los costes y la liquidación de verdad, que es
lo que hace este módulo.

Qué es la hipótesis nula aquí
─────────────────────────────
La afirmación que sostiene el carry no es «acierto la dirección» sino **«el
funding es sistemáticamente positivo lo bastante como para pagar los costes»**.
Su negación es que el funding no tiene sesgo de signo: cobra tanto como paga.

Por eso el nulo se construye **aleatorizando el signo** de la serie de funding y
conservando sus magnitudes. Eso destruye exactamente la afirmación bajo prueba
—el sesgo positivo— dejando intacto todo lo demás: la escala del funding, su
volatilidad y la estructura de costes. Si el carry observado no supera el
percentil 95 de esa distribución, lo que se está cobrando no es el sesgo
estructural del mercado: es una racha.

Bootstrapear la serie sin tocar el signo NO serviría: preservaría la media, que
es justo lo que se quiere poner a prueba.

Capa de dominio: NumPy puro, sin ORM ni red.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Liquidaciones de funding al año con la cadencia estándar de 8 horas.
PERIODS_PER_YEAR = 1095.0

# Margen de mantenimiento típico de un perpetuo grande en Binance/Bybit para
# tamaños modestos. Por encima de esta fracción del nocional, la posición se
# liquida. Se deja explícito porque cambia por venue y por tramo de tamaño, y
# esconderlo dentro de una fórmula haría que la distancia a liquidación
# pareciera una propiedad del mercado en lugar de un parámetro del contrato.
DEFAULT_MAINTENANCE_MARGIN = 0.005


@dataclass(frozen=True)
class CarryCosts:
    """
    Lo que cuesta montar y deshacer la posición, y mantener el colateral.

    Las comisiones son POR PATA Y POR LADO: montar el delta-neutral son dos
    órdenes (comprar spot, vender perp) y deshacerlo otras dos. Contar solo una
    es el error que convierte un carry mediocre en uno excelente sobre el papel.
    """
    taker_fee_bps: float = 5.0        # por orden
    slippage_bps: float = 2.0         # por orden
    # Coste de oportunidad del capital inmovilizado, anualizado. Cero por
    # defecto: es una decisión de quien opera, no un dato del mercado.
    capital_cost_annual_pct: float = 0.0

    @property
    def round_trip_bps(self) -> float:
        """Cuatro órdenes: dos patas, entrada y salida."""
        return 4.0 * (self.taker_fee_bps + self.slippage_bps)


@dataclass(frozen=True)
class CarryPosition:
    """Tamaño y margen de la posición."""
    notional_usd: float = 10_000.0
    # Fracción del nocional depositada como margen en la pata corta. Un margen
    # del 20 % equivale a 5x de apalancamiento en esa pata; cuanto menor, más
    # capital eficiente y más cerca de la liquidación.
    margin_pct: float = 0.20
    maintenance_margin: float = DEFAULT_MAINTENANCE_MARGIN


def liquidation_price(entry_price: float, position: CarryPosition) -> float:
    """
    Precio al que se liquida la pata CORTA.

    Un corto pierde cuando el precio sube. Se liquida cuando la pérdida consume
    el margen depositado menos el de mantenimiento:

        precio_liq = entrada · (1 + margen − mantenimiento)

    Es la cifra que convierte «esto rinde un 12 % anual» en una decisión: un
    carry excelente con la liquidación al 8 % de distancia no es un carry
    excelente, es una apuesta a que no haya un día malo.
    """
    if entry_price <= 0:
        return float("nan")
    colchon = max(position.margin_pct - position.maintenance_margin, 0.0)
    return float(entry_price * (1.0 + colchon))


def funding_income(rates, notional_usd: float) -> np.ndarray:
    """
    Ingreso de funding por periodo para la pata CORTA, en USD.

    Convenio del motor: `rate` positivo = los largos pagan. El corto del
    delta-neutral está al otro lado, así que **cobra** cuando el rate es
    positivo y paga cuando es negativo. Es el signo contrario al del resto del
    motor, que es long-only, y por eso se escribe aquí explícitamente en vez de
    reutilizar la función de coste.
    """
    arr = np.asarray(list(rates), dtype=float)
    arr = arr[np.isfinite(arr)]
    return arr * float(notional_usd)


def simulate_carry(rates, position: CarryPosition | None = None,
                   costs: CarryCosts | None = None,
                   entry_price: float | None = None,
                   max_price: float | None = None) -> dict:
    """
    Resultado de mantener el delta-neutral durante toda la serie de funding.

    Devuelve el flujo bruto, los costes, el neto, el rendimiento anualizado
    sobre el CAPITAL REALMENTE INMOVILIZADO —no sobre el nocional— y, si se dan
    los precios, si la pata corta habría sido liquidada.

    El rendimiento se expresa sobre el capital inmovilizado a propósito. Sobre
    el nocional saldría un número más pequeño y más halagüeño de gestionar, pero
    el capital que hay que tener parado para sostener esto es el spot completo
    más el margen del corto, y es sobre ese sobre el que se decide si compensa.
    """
    pos = position or CarryPosition()
    cst = costs or CarryCosts()

    ingresos = funding_income(rates, pos.notional_usd)
    n = int(ingresos.size)
    if n == 0:
        return {"periods": 0, "net_usd": 0.0, "verdict": "SIN_DATOS",
                "note": "Sin histórico de financiación para este tramo."}

    bruto = float(ingresos.sum())
    coste_ordenes = pos.notional_usd * cst.round_trip_bps / 10_000.0

    anos = n / PERIODS_PER_YEAR
    # Capital inmovilizado: el spot entero más el margen de la pata corta.
    capital = pos.notional_usd * (1.0 + pos.margin_pct)
    coste_capital = capital * cst.capital_cost_annual_pct / 100.0 * anos

    neto = bruto - coste_ordenes - coste_capital
    anualizado = (neto / capital / anos * 100.0) if (capital > 0 and anos > 0) else 0.0

    liquidado = None
    precio_liq = None
    if entry_price is not None:
        precio_liq = liquidation_price(entry_price, pos)
        if max_price is not None:
            liquidado = bool(max_price >= precio_liq)

    return {
        "periods": n,
        "years": round(anos, 4),
        "gross_funding_usd": round(bruto, 2),
        "order_costs_usd": round(coste_ordenes, 2),
        "capital_cost_usd": round(coste_capital, 2),
        "net_usd": round(neto, 2),
        "capital_usd": round(capital, 2),
        "net_annualized_pct": round(anualizado, 3),
        "positive_periods_pct": round(float(np.mean(ingresos > 0)) * 100, 1),
        "liquidation_price": round(precio_liq, 2) if precio_liq else None,
        "liquidated": liquidado,
        "round_trip_bps": cst.round_trip_bps,
    }


def shock_margin_probability(rates, position: CarryPosition | None = None,
                             shock_pct: float = 15.0) -> dict:
    """
    ¿Qué margen queda si el precio salta un `shock_pct` de golpe?

    No es una probabilidad estimada de un modelo: es la respuesta determinista a
    «si mañana sube un 15 %, ¿sigo vivo?». Se prefiere así deliberadamente. Una
    probabilidad de liquidación requiere un modelo de la cola de la distribución
    de precios, y esa cola es precisamente lo que peor se estima en cripto; el
    escenario declarado no necesita ese modelo y se entiende sin él.
    """
    pos = position or CarryPosition()
    colchon = pos.margin_pct - pos.maintenance_margin
    shock = shock_pct / 100.0
    sobrevive = shock < colchon
    return {
        "shock_pct": shock_pct,
        "buffer_pct": round(colchon * 100, 2),
        "survives": bool(sobrevive),
        "margin_left_pct": round((colchon - shock) * 100, 2),
        "note": (
            f"Con un margen del {pos.margin_pct * 100:.0f} % el colchón hasta la "
            f"liquidación es del {colchon * 100:.1f} %. Un salto del {shock_pct:.0f} % "
            + ("lo aguanta." if sobrevive else "LIQUIDA la pata corta.")
        ),
    }


def null_distribution(rates, position: CarryPosition | None = None,
                      costs: CarryCosts | None = None,
                      n_draws: int = 1000, seed: int = 42) -> dict:
    """
    Qué carry neto saldría si el funding no tuviera sesgo de signo.

    Se aleatoriza el SIGNO de cada liquidación conservando su magnitud. Eso
    destruye exactamente la afirmación bajo prueba —que el funding es
    sistemáticamente positivo— y deja intacto todo lo demás: la escala, la
    volatilidad y la estructura de costes.

    El percentil 95 de esa distribución es el listón. Por debajo de él, lo
    cobrado no se distingue de una racha afortunada de signos.
    """
    pos = position or CarryPosition()
    cst = costs or CarryCosts()
    arr = np.asarray(list(rates), dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {"n_draws": 0, "p95_usd": None,
                "note": "Sin histórico de financiación para construir el nulo."}

    magnitudes = np.abs(arr)
    rng = np.random.default_rng(seed)
    netos = np.empty(n_draws)
    coste_ordenes = pos.notional_usd * cst.round_trip_bps / 10_000.0
    anos = arr.size / PERIODS_PER_YEAR
    capital = pos.notional_usd * (1.0 + pos.margin_pct)
    coste_capital = capital * cst.capital_cost_annual_pct / 100.0 * anos

    for i in range(n_draws):
        signos = rng.choice((-1.0, 1.0), size=magnitudes.size)
        bruto = float(np.sum(signos * magnitudes) * pos.notional_usd)
        netos[i] = bruto - coste_ordenes - coste_capital

    return {
        "n_draws": int(n_draws),
        "p95_usd": round(float(np.percentile(netos, 95)), 2),
        "median_usd": round(float(np.median(netos)), 2),
        "method": "SIGN_RANDOMIZATION",
        "note": (
            "Nulo por aleatorización de signo: conserva la magnitud y la "
            "volatilidad del funding y destruye solo su sesgo positivo, que es "
            "la afirmación que sostiene el carry."
        ),
    }


def carry_verdict(observed: dict, null: dict, shock: dict) -> dict:
    """
    ¿Se opera esto con dinero real?

    Tres condiciones, y las tres son necesarias:

      1. **Neto positivo.** Después de las cuatro comisiones y del coste de
         capital. Un bruto positivo con neto negativo es el resultado más común
         y el que más se enseña sin decir que es bruto.
      2. **Por encima del nulo.** El carry tiene que superar el percentil 95 de
         lo que daría un funding sin sesgo de signo; si no, se está cobrando una
         racha.
      3. **Sobrevive al shock declarado.** Un carry excelente con la liquidación
         a la vuelta de la esquina no es un carry excelente.

    El criterio de abandono del protocolo es explícito: si no supera el nulo, no
    se opera con dinero real. Aquí no se suaviza.
    """
    neto = observed.get("net_usd")
    p95 = null.get("p95_usd")
    if neto is None or p95 is None:
        return {"verdict": "SIN_DATOS", "tradeable": False,
                "note": "Faltan datos para emitir un veredicto."}

    positivo = neto > 0
    bate_nulo = neto > p95
    aguanta = bool(shock.get("survives"))
    operable = positivo and bate_nulo and aguanta

    if operable:
        veredicto = "OPERABLE"
        nota = (f"Neto {neto:+,.0f} USD por encima del nulo ({p95:+,.0f}) y el "
                f"colchón aguanta un shock del {shock.get('shock_pct')} %.")
    elif not positivo:
        veredicto = "NO_CUBRE_COSTES"
        nota = (f"El flujo bruto no cubre las cuatro comisiones: neto "
                f"{neto:+,.0f} USD.")
    elif not bate_nulo:
        veredicto = "INDISTINGUIBLE_DEL_NULO"
        nota = (f"Neto {neto:+,.0f} USD, pero un funding sin sesgo de signo daría "
                f"{p95:+,.0f} en su percentil 95: lo cobrado es una racha, no el "
                "sesgo estructural del mercado.")
    else:
        veredicto = "RIESGO_DE_LIQUIDACION"
        nota = (f"El carry es rentable pero un shock del {shock.get('shock_pct')} % "
                "liquida la pata corta: hay que bajar apalancamiento antes de "
                "operarlo.")

    return {
        "verdict": veredicto,
        "tradeable": operable,
        "covers_costs": positivo,
        "beats_null": bate_nulo,
        "survives_shock": aguanta,
        "note": nota,
    }
