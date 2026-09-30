"""
option_moments.py — Lo que el mercado de opciones dice que va a pasar.

Por qué esto y no otra cosa
───────────────────────────
`edge_test` estableció cuál es la única pregunta que la muestra de esta
plataforma puede responder: **la magnitud del movimiento**, no su dirección. Todo
lo que refuerce esa pregunta vale más que cualquier feature nueva, y las opciones
son la única fuente que da una medida **prospectiva** de ella: no lo que la
volatilidad ha sido, sino lo que el mercado está pagando por cubrirse de la que
viene.

La literatura sobre cripto es específica al respecto. Con opciones de BTC de
Deribit se construyen varianza implícita, prima de riesgo de varianza (VRP) y
volatilidad de la volatilidad (VoV); los factores implícitos —especialmente
VoV— predicen el exceso de retorno de BTC en varios horizontes y superan a los
predictores de sentimiento y de estilo de renta variable. Y a diferencia de la
renta variable, la varianza sola no basta en cripto: los momentos de orden
superior aportan información incremental.

Hay además un hecho propio del activo que conviene no perder: la prima de riesgo
de varianza de Bitcoin la mueve el lado **alcista**, al contrario que el S&P 500,
donde la mueve el bajista. Un indicador de miedo copiado de renta variable llega
con el signo al revés.

Qué se calcula aquí
───────────────────
· **Varianza implícita libre de modelo** — la integral de precios de opciones
  fuera del dinero ponderados por `1/K²`, que es la construcción del VIX. No
  supone Black-Scholes: mide la variación cuadrática esperada bajo la medida
  neutral al riesgo.
· **Risk reversal a 25 delta** — la diferencia de volatilidad implícita entre la
  call y la put de 25 delta. Es la asimetría: quién paga más por cubrirse.
· **Butterfly a 25 delta** — cuánto sobresalen las alas sobre el dinero. Es
  convexidad: cuánto se paga por los extremos.
· **Prima de riesgo de varianza** — implícita menos realizada. Lo que cobra
  quien vende volatilidad, y el signo de si está cara o barata.

Tres límites que se declaran en cada salida
───────────────────────────────────────────
**1. La truncación subestima.** La fórmula es una integral sobre un rango
infinito de strikes y se aproxima con una suma sobre los que existen. El
integrando es siempre positivo, así que cortar las colas **siempre infravalora**
la varianza, nunca lo contrario. En cripto las cadenas son más estrechas que en
renta variable, y el sesgo es mayor. La salida reporta hasta dónde llega la
cadena en desviaciones típicas para que se pueda juzgar.

**2. La discretización también.** `ΔK` se aproxima con la media de las distancias
a los strikes vecinos. Con pocos strikes ese error crece, y se reporta cuántos
hubo.

**3. La volatilidad de la volatilidad no sale de una foto.** VoV —el factor con
más contenido predictivo según la literatura— es la variabilidad de la varianza
implícita a lo largo del tiempo, así que necesita SERIE. Desde un único snapshot
no se puede calcular, y devolver algo en su lugar sería inventarlo. Por eso este
módulo se limita a producir los momentos de cada instante, y el archivado los
convierte en serie.

Capa de dominio: NumPy puro, sin red ni ORM. Todos los precios y strikes en la
MISMA moneda (USD); el adaptador de Deribit es quien convierte, porque allí las
primas se cotizan en unidades del subyacente.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# Delta de referencia para las alas. 25 es la convención de mesa en divisas y en
# cripto: suficientemente fuera del dinero para capturar la asimetría y
# suficientemente líquido para que el precio signifique algo. A 10 delta la
# cadena de cripto suele estar vacía o con horquillas absurdas.
WING_DELTA = 0.25

# Strikes mínimos para que la integral signifique algo. Con menos, el error de
# discretización domina el resultado y el número es decorativo.
MIN_STRIKES = 5

# Días al año, para anualizar.
DAYS_PER_YEAR = 365.0


@dataclass(frozen=True)
class OptionQuote:
    """
    Una fila de la cadena: un strike con sus dos patas.

    `call_price` y `put_price` en la misma moneda que `strike`. Las volatilidades
    implícitas en fracción (0,65 = 65 %), no en porcentaje — Deribit las publica
    en porcentaje y el adaptador divide.

    `call_delta` se espera en [0, 1] y `put_delta` en [-1, 0], que es el convenio
    habitual. Se normaliza por valor absoluto al buscar las alas para no depender
    de él.
    """
    strike: float
    call_price: float | None = None
    put_price: float | None = None
    call_iv: float | None = None
    put_iv: float | None = None
    call_delta: float | None = None
    put_delta: float | None = None


def _otm_price(q: OptionQuote, forward: float) -> float | None:
    """
    Precio de la opción FUERA del dinero en este strike.

    Se usa la fuera del dinero y no la media de las dos porque es la que tiene
    liquidez: la dentro del dinero cotiza con horquilla ancha y su precio está
    dominado por el valor intrínseco, que no aporta información sobre la
    volatilidad. Es la elección del VIX y no es cosmética.
    """
    if q.strike < forward:
        return q.put_price
    if q.strike > forward:
        return q.call_price
    # En el strike justo en el forward se promedian las dos patas, que es lo que
    # hace la metodología oficial para el strike de referencia.
    precios = [p for p in (q.call_price, q.put_price) if p is not None and p > 0]
    return float(np.mean(precios)) if precios else None


def model_free_variance(quotes: list[OptionQuote], forward: float,
                        days_to_expiry: float, rate: float = 0.0) -> dict:
    """
    Varianza implícita libre de modelo — la construcción del VIX.

        V = (2·e^{rT}/T) · Σ_i (ΔK_i / K_i²) · Q(K_i)  −  (1/T)·(F/K* − 1)²

    con `ΔK_i` la media de las distancias a los strikes vecinos, `Q(K_i)` el
    precio de la opción fuera del dinero y `K*` el primer strike por debajo del
    forward.

    «Libre de modelo» significa que no supone Black-Scholes: la integral mide la
    variación cuadrática esperada bajo la medida neutral al riesgo, sea cual sea
    el proceso. La volatilidad implícita de una sola opción sí supone un modelo;
    esto no.

    Devuelve la varianza anualizada, su raíz —la volatilidad implícita del
    índice— y el diagnóstico de cuánto se puede confiar en ella.
    """
    T = float(days_to_expiry) / DAYS_PER_YEAR
    if T <= 0 or forward <= 0:
        return {"available": False,
                "note": "Vencimiento o forward no válidos."}

    filas = sorted((q for q in quotes if q.strike > 0), key=lambda q: q.strike)
    usables = [(q.strike, _otm_price(q, forward)) for q in filas]
    usables = [(k, p) for k, p in usables if p is not None and p > 0]
    if len(usables) < MIN_STRIKES:
        return {
            "available": False,
            "n_strikes": len(usables),
            "note": (f"Solo {len(usables)} strikes con precio fuera del dinero y "
                     f"hacen falta {MIN_STRIKES}. Con menos, el error de "
                     "discretización domina y el número sería decorativo."),
        }

    strikes = np.array([k for k, _ in usables], dtype=float)
    precios = np.array([p for _, p in usables], dtype=float)

    # ΔK: media de las distancias a los vecinos; en los extremos, la distancia al
    # único vecino que hay.
    dk = np.empty_like(strikes)
    dk[1:-1] = (strikes[2:] - strikes[:-2]) / 2.0
    dk[0] = strikes[1] - strikes[0]
    dk[-1] = strikes[-1] - strikes[-2]

    suma = float(np.sum(dk / strikes ** 2 * precios))
    # K*: primer strike por debajo del forward (o el menor, si todos están arriba).
    debajo = strikes[strikes <= forward]
    k_star = float(debajo[-1]) if debajo.size else float(strikes[0])

    varianza = (2.0 * np.exp(rate * T) / T) * suma - (1.0 / T) * (forward / k_star - 1.0) ** 2
    if not np.isfinite(varianza) or varianza <= 0:
        return {"available": False, "n_strikes": len(usables),
                "note": ("La integral sale no positiva: la cadena es demasiado "
                         "estrecha o los precios son inconsistentes.")}

    vol = float(np.sqrt(varianza))
    # Cobertura de la cadena en desviaciones típicas del propio movimiento
    # esperado. Es la cifra que permite juzgar cuánto pesa la truncación: una
    # cadena que solo llega a ±1σ deja fuera una cola enorme.
    sigma_T = vol * np.sqrt(T) * forward
    cobertura_baja = (forward - strikes[0]) / sigma_T if sigma_T > 0 else 0.0
    cobertura_alta = (strikes[-1] - forward) / sigma_T if sigma_T > 0 else 0.0

    return {
        "available": True,
        "variance_annual": round(float(varianza), 6),
        "implied_vol_annual": round(vol, 6),
        "implied_vol_annual_pct": round(vol * 100, 2),
        "days_to_expiry": round(float(days_to_expiry), 2),
        "n_strikes": len(usables),
        "forward": round(float(forward), 2),
        "k_star": round(k_star, 2),
        "strike_range": [round(float(strikes[0]), 2), round(float(strikes[-1]), 2)],
        "coverage_sigma_down": round(float(cobertura_baja), 2),
        "coverage_sigma_up": round(float(cobertura_alta), 2),
        "method": "MODEL_FREE_VIX",
        "note": (
            f"Varianza libre de modelo sobre {len(usables)} strikes. La cadena "
            f"cubre {cobertura_baja:.1f}σ por abajo y {cobertura_alta:.1f}σ por "
            "arriba; lo que queda fuera SIEMPRE infravalora la varianza, porque el "
            "integrando es positivo y truncarlo solo puede restar."
        ),
    }


def _iv_at_delta(quotes: list[OptionQuote], target: float, side: str) -> float | None:
    """
    Volatilidad implícita en el delta objetivo, por interpolación.

    Se interpola en |delta| y no en strike a propósito: el delta es comparable
    entre vencimientos y entre niveles de precio, y el strike no. «La put de 25
    delta» significa lo mismo hoy con BTC a 40.000 que a 120.000; «la put de
    strike 35.000» no significa nada estable.
    """
    puntos = []
    for q in quotes:
        iv = q.call_iv if side == "call" else q.put_iv
        d = q.call_delta if side == "call" else q.put_delta
        if iv is None or d is None or iv <= 0:
            continue
        puntos.append((abs(float(d)), float(iv)))
    if len(puntos) < 2:
        return None

    puntos.sort()
    deltas = np.array([d for d, _ in puntos])
    ivs = np.array([v for _, v in puntos])
    if target < deltas[0] or target > deltas[-1]:
        # Extrapolar la sonrisa es inventarse las alas, que es exactamente donde
        # vive la información que se busca. Se devuelve None.
        return None
    return float(np.interp(target, deltas, ivs))


def wing_structure(quotes: list[OptionQuote], delta: float = WING_DELTA) -> dict:
    """
    Asimetría y convexidad de la sonrisa, en las alas de `delta`.

    · **Risk reversal** = IV(call) − IV(put). Positivo significa que se paga más
      por la subida que por la bajada. En renta variable es casi siempre negativo
      —el miedo es a caer— y en cripto **cambia de signo según el régimen**, que
      es justo lo que lo hace informativo aquí y no allí.
    · **Butterfly** = media de las alas − IV del dinero. Cuánto sobresalen los
      extremos: cuánto se paga por un movimiento grande en cualquier dirección.

    Si la cadena no llega al delta pedido se devuelve None en vez de extrapolar.
    Extrapolar la sonrisa es inventarse precisamente las alas, que es donde vive
    la información buscada.
    """
    iv_call = _iv_at_delta(quotes, delta, "call")
    iv_put = _iv_at_delta(quotes, delta, "put")
    iv_atm = _iv_at_delta(quotes, 0.50, "call") or _iv_at_delta(quotes, 0.50, "put")

    if iv_call is None or iv_put is None:
        return {
            "available": False,
            "delta": delta,
            "note": (f"La cadena no llega a {delta:.0%} de delta en las dos patas. "
                     "No se extrapola: inventar las alas es inventar justo el dato "
                     "que se busca."),
        }

    rr = iv_call - iv_put
    bf = (iv_call + iv_put) / 2.0 - iv_atm if iv_atm else None

    return {
        "available": True,
        "delta": delta,
        "iv_call_pct": round(iv_call * 100, 2),
        "iv_put_pct": round(iv_put * 100, 2),
        "iv_atm_pct": round(iv_atm * 100, 2) if iv_atm else None,
        "risk_reversal_pct": round(rr * 100, 2),
        "butterfly_pct": round(bf * 100, 2) if bf is not None else None,
        "skew_side": "ALCISTA" if rr > 0 else ("BAJISTA" if rr < 0 else "SIMÉTRICO"),
        "note": (
            f"Risk reversal de {rr * 100:+.2f} puntos: se paga más por la "
            + ("SUBIDA" if rr > 0 else "BAJADA")
            + ". En cripto este signo cambia con el régimen, al contrario que en "
              "renta variable, donde es casi siempre negativo — un indicador de "
              "miedo copiado de allí llegaría con el signo al revés."
        ),
    }


def variance_risk_premium(implied_variance_annual: float,
                          realized_variance_annual: float) -> dict:
    """
    Prima de riesgo de varianza: implícita menos realizada.

    Es lo que cobra quien vende volatilidad. Positiva significa que las opciones
    estaban caras respecto a lo que después ocurrió; negativa, que estaban
    baratas y quien vendió perdió.

    Una advertencia que hay que llevar pegada al número: esto **no es un carry
    cosechable** sin más. La prima existe porque quien vende asume el riesgo de
    la cola, y las colas de cripto son brutales: la serie de beneficios de vender
    volatilidad es de muchas ganancias pequeñas y una pérdida enorme, que es el
    mismo perfil de pago que hace peligroso al martingala. Medirla es útil;
    cosecharla sin límite de pérdida es otra cosa.
    """
    iv = float(implied_variance_annual)
    rv = float(realized_variance_annual)
    if iv <= 0 or rv < 0:
        return {"available": False,
                "note": "Varianza implícita o realizada no válidas."}

    vrp = iv - rv
    ratio = iv / rv if rv > 0 else None
    return {
        "available": True,
        "implied_vol_pct": round(float(np.sqrt(iv)) * 100, 2),
        "realized_vol_pct": round(float(np.sqrt(rv)) * 100, 2),
        "vrp_variance": round(vrp, 6),
        "vrp_vol_points": round((float(np.sqrt(iv)) - float(np.sqrt(rv))) * 100, 2),
        "iv_rv_ratio": round(ratio, 3) if ratio else None,
        "expensive": bool(vrp > 0),
        "note": (
            ("La volatilidad implícita está por encima de la realizada: vender "
             "volatilidad ha sido rentable en este tramo. NO es un carry "
             "cosechable sin más — la prima paga el riesgo de cola, y en cripto "
             "la cola es una pérdida enorme tras muchas ganancias pequeñas.")
            if vrp > 0 else
            ("La volatilidad implícita está por DEBAJO de la realizada: el mercado "
             "estaba infravalorando el movimiento y quien vendió volatilidad "
             "perdió.")
        ),
    }
