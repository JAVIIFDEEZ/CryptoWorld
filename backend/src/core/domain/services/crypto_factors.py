"""
crypto_factors.py — Contra qué hay que medir una estrategia de cripto.

El hueco que cierra
───────────────────
Todo este motor mide Sharpe. Contra nada. Una estrategia con Sharpe 2 puede ser
beta de mercado apalancada, exposición a momento de tres semanas, o un sesgo
hacia monedas pequeñas — y en los tres casos el Sharpe sale igual de bien sin que
haya una sola idea propia dentro.

Liu, Tsyvinski y Wu (*Common Risk Factors in Cryptocurrency*, Journal of Finance
77(2), 2022) construyeron el equivalente cripto del modelo de tres factores:
mercado (CMKT), tamaño (CSMB) y momento (CMOM). Su resultado es el que hace falta
tener delante antes de celebrar cualquier backtest: de las **nueve** estrategias
long-short que producían retornos significativos por separado, **ninguna
conserva alfa significativo** una vez ajustada por esos tres factores.

Es decir: nueve anomalías aparentes eran las mismas tres exposiciones repetidas.
Medir alfa en vez de Sharpe es lo que distingue eso de un descubrimiento.

Es además la misma idea que la auditoría señalaba citando a Numerai: el valor de
una señal no es su Sharpe, es su **contribución ortogonal** a lo que ya existe.
Aquí eso se vuelve un número con su intervalo.

Dos decisiones que el paper no puede tomar por nosotros
──────────────────────────────────────────────────────
**1. El tamaño se aproxima con volumen en dólares, no con capitalización.**
LTW ordenan por capitalización de mercado. Esta plataforma guarda la
capitalización como una FOTO actual, no como serie histórica: usarla para
ordenar carteras del pasado sería lookahead puro —se estaría clasificando 2024
con lo que se sabe en 2026— y de los que peor se detecta, porque el número parece
un dato. El volumen en dólares (volumen × cierre) sí está en el almacén OHLCV
con sello temporal, y en el propio paper vive en el MISMO grupo de factores que
la capitalización: CSMB agrupa capitalización, precio, precio máximo, volumen en
dólares y su desviación. La sustitución es defendible por eso y no por comodidad.

**2. Los quintiles necesitan universo.** Con 1.700 monedas, un quintil son 340
carteras y la ordenación significa algo. Con 10 monedas, un quintil son 2 y el
factor es ruido con nombre de factor. Este módulo **se niega** por debajo de un
mínimo en lugar de devolver una serie que parece un factor. Es la diferencia
entre no poder medir y medir mal.

Capa de dominio: numpy y pandas, sin ORM ni red.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Cadencia de rebalanceo, en días. Semanal es la del paper, y no es arbitraria:
# el momento de cripto vive en horizontes de una a cuatro semanas y se invierte
# más allá del mes, así que rebalancear mensualmente mediría la reversión.
REBALANCE_DAYS = 7

# Quintiles, como en el paper. La cartera larga-corta es Q5 − Q1.
N_QUANTILES = 5

# Retardos de momento que el paper encuentra significativos, en semanas. CMOM
# recoge los de dos, tres y cuatro; el de una semana lo comparten CSMB y CMOM.
MOMENTUM_LOOKBACK_WEEKS = 3

# Universo mínimo para que una ordenación por quintiles no sea ruido. Con menos
# de esto hay menos de dos activos por quintil y la cartera larga-corta es una
# apuesta sobre dos monedas, no un factor.
MIN_UNIVERSE = 10

FACTOR_NAMES = ("CMKT", "CSMB", "CMOM")

# Periodos al año con rebalanceo semanal, para anualizar el alfa.
PERIODS_PER_YEAR = 365.0 / REBALANCE_DAYS

# Alfa mínimo, anualizado, para que merezca llamarse alfa.
#
# Hace falta porque la significancia estadística sola tiene un modo degenerado
# real: una estrategia que es CASI exactamente una combinación de los factores
# —un replicador de índice apalancado, por ejemplo— deja residuos minúsculos, y
# con residuos minúsculos el error estándar tiende a cero y el estadístico t se
# dispara sobre un alfa económicamente nulo. Se vio en la calibración: una
# estrategia construida como 1,5 × CMKT daba alfa de 0,0000 con t = 6,3.
#
# El listón es el mismo principio que ya gobierna el edge direccional y la
# correlación de volatilidad en este motor: un p-valor pequeño no es un efecto
# grande. Un punto porcentual anual es además el suelo por debajo del cual nada
# sobrevive a las comisiones de rebalancear cada semana.
MIN_ECONOMIC_ALPHA_ANNUAL = 0.01

# Tope al que se recorta cualquier estadístico t publicado.
#
# Con un ajuste casi perfecto los residuos son del orden de 1e-17 y los t salen
# del orden de 1e14. El número es aritméticamente correcto y, impreso, destruye la
# credibilidad del informe entero: quien lee «t = +469074387171099» deja de
# creerse las cifras de al lado, y con razón. Recortarlo no pierde información
# —cualquier cosa por encima de 999 significa lo mismo: ajuste degenerado— y
# `degenerate_fit` dice explícitamente que ha pasado.
T_STAT_CAP = 999.0

# R² por encima del cual la estrategia ES una combinación de los factores y los
# errores estándar dejan de significar nada.
DEGENERATE_R2 = 0.9999


def _long_short(frame: pd.DataFrame, sort_col: str, weight_col: str) -> float:
    """
    Retorno de la cartera Q5 − Q1, ponderada por valor dentro de cada quintil.

    Ponderar por valor y no por igual es lo que evita que el factor esté
    dominado por las monedas más pequeñas, que son justo las que tienen el
    retorno más ruidoso y el coste de ejecución más alto — un factor
    equiponderado en cripto mide sobre todo microcaps ilíquidas.
    """
    if len(frame) < N_QUANTILES:
        return float("nan")

    rangos = frame[sort_col].rank(method="first")
    # `qcut` sobre los RANGOS y no sobre los valores: los factores de cripto
    # tienen colas brutales y los cortes por valor dejarían quintiles vacíos.
    try:
        cubos = pd.qcut(rangos, N_QUANTILES, labels=False, duplicates="drop")
    except ValueError:
        return float("nan")

    alto = frame[cubos == cubos.max()]
    bajo = frame[cubos == cubos.min()]
    if alto.empty or bajo.empty:
        return float("nan")

    def _vw(bloque: pd.DataFrame) -> float:
        pesos = bloque[weight_col].to_numpy(dtype=float)
        pesos = np.where(np.isfinite(pesos) & (pesos > 0), pesos, 0.0)
        if pesos.sum() <= 0:
            return float(bloque["ret"].mean())
        return float(np.average(bloque["ret"].to_numpy(dtype=float), weights=pesos))

    return _vw(alto) - _vw(bajo)


def build_factors(panel: pd.DataFrame) -> dict:
    """
    Construye CMKT, CSMB y CMOM a partir de un panel de retornos semanales.

    `panel` necesita las columnas:
      · `period`  — índice de semana (entero o fecha); define el rebalanceo.
      · `symbol`  — activo.
      · `ret`     — retorno de ESA semana (el que se realiza).
      · `size`    — volumen en dólares de la semana ANTERIOR (ver módulo).
      · `mom`     — retorno acumulado de las `MOMENTUM_LOOKBACK_WEEKS` semanas
                    previas, sin incluir la actual.

    Las columnas de ordenación (`size`, `mom`) tienen que estar desplazadas por
    quien construye el panel: aquí se ordena con lo que llega, y si llega con la
    información de la misma semana que se está midiendo, el factor sale
    espectacular y es mentira. Esa responsabilidad se declara en vez de
    escondrse porque es donde se comete la fuga.

    Devuelve las tres series y un informe de por qué se puede o no confiar en
    ellas.
    """
    requeridas = {"period", "symbol", "ret", "size", "mom"}
    faltan = requeridas - set(panel.columns)
    if faltan:
        return {"available": False, "factors": None,
                "note": f"Faltan columnas en el panel: {sorted(faltan)}."}

    universo = int(panel.groupby("period")["symbol"].nunique().median())
    if universo < MIN_UNIVERSE:
        return {
            "available": False,
            "factors": None,
            "universe_median": universo,
            "note": (
                f"Universo insuficiente: {universo} activos por periodo y hacen "
                f"falta {MIN_UNIVERSE} para que un quintil tenga al menos dos. "
                "Con menos, la cartera larga-corta es una apuesta sobre dos "
                "monedas y no un factor; se prefiere no devolver una serie que "
                "parecería uno."
            ),
        }

    filas = []
    for period, grupo in panel.groupby("period", sort=True):
        limpio = grupo.replace([np.inf, -np.inf], np.nan).dropna(
            subset=["ret", "size", "mom"])
        if len(limpio) < MIN_UNIVERSE:
            continue

        pesos = limpio["size"].to_numpy(dtype=float)
        pesos = np.where(np.isfinite(pesos) & (pesos > 0), pesos, 0.0)
        cmkt = (float(np.average(limpio["ret"].to_numpy(dtype=float), weights=pesos))
                if pesos.sum() > 0 else float(limpio["ret"].mean()))

        # CSMB: pequeñas MENOS grandes, así que se invierte el signo de la
        # ordenación por tamaño. Q5−Q1 sobre tamaño daría grandes menos pequeñas,
        # que es el factor con el signo al revés.
        csmb = -_long_short(limpio, "size", "size")
        cmom = _long_short(limpio, "mom", "size")

        filas.append({"period": period, "CMKT": cmkt, "CSMB": csmb, "CMOM": cmom,
                      "n_assets": int(len(limpio))})

    if not filas:
        return {"available": False, "factors": None,
                "note": "Ningún periodo con universo suficiente tras limpiar."}

    factors = pd.DataFrame(filas).set_index("period")
    return {
        "available": True,
        "factors": factors,
        "periods": int(len(factors)),
        "universe_median": universo,
        "rebalance_days": REBALANCE_DAYS,
        "n_quantiles": N_QUANTILES,
        "size_proxy": "DOLLAR_VOLUME",
        "note": (
            f"{len(factors)} periodos con {universo} activos de mediana. El tamaño "
            "se aproxima con volumen en dólares porque la capitalización solo "
            "existe como foto actual y usarla para ordenar el pasado sería "
            "lookahead; en el paper vive en el mismo grupo de factores."
        ),
        "reference": ("Liu, Tsyvinski y Wu (2022), «Common Risk Factors in "
                      "Cryptocurrency», Journal of Finance 77(2), 1133-1177."),
    }


def _newey_west_ols(y: np.ndarray, X: np.ndarray, lags: int) -> tuple:
    """
    Mínimos cuadrados con errores estándar robustos a autocorrelación.

    Los errores estándar clásicos suponen residuos independientes. Los retornos
    de una estrategia no lo son: las posiciones se solapan, los regímenes duran
    semanas y la volatilidad se agrupa. Usar los clásicos estrecha el intervalo y
    convierte ruido en alfa significativo — es el mismo error que la falta de
    purga, cometido en la inferencia en vez de en la partición.
    """
    n, k = X.shape
    XtX_inv = np.linalg.pinv(X.T @ X)
    beta = XtX_inv @ X.T @ y
    resid = y - X @ beta

    # Matriz de Newey-West con ventana de Bartlett.
    S = (X * resid[:, None]).T @ (X * resid[:, None])
    for lag in range(1, lags + 1):
        peso = 1.0 - lag / (lags + 1)
        Xu_t = X[lag:] * resid[lag:, None]
        Xu_l = X[:-lag] * resid[:-lag, None]
        Gamma = Xu_t.T @ Xu_l
        S += peso * (Gamma + Gamma.T)

    cov = XtX_inv @ S @ XtX_inv
    se = np.sqrt(np.maximum(np.diag(cov), 0.0))
    return beta, se, resid


def factor_alpha(strategy_returns, factors: pd.DataFrame,
                 lags: int | None = None) -> dict:
    """
    ¿Queda algo de esta estrategia después de descontar los tres factores?

    Regresa los retornos de la estrategia sobre CMKT, CSMB y CMOM. El intercepto
    es el **alfa**: el retorno que no explica ninguna de las tres exposiciones.
    Los errores estándar son de Newey-West, porque los residuos de una estrategia
    están autocorrelacionados por construcción.

    Lo que hay que leer, en este orden:

      1. **alpha_t** — si no supera 2 en valor absoluto, la estrategia no ha
         demostrado aportar nada que no se consiga con los tres factores. Es el
         resultado que obtuvieron LTW para las nueve estrategias que probaron.
      2. **betas** — a qué está expuesta en realidad. Una beta de mercado de 1,5
         con alfa cero es mercado apalancado, y eso se compra más barato.
      3. **r_squared** — cuánto de su variación es factores. Alto con alfa cero es
         el caso más común y el más caro de confundir con un descubrimiento.
    """
    y = np.asarray(list(strategy_returns), dtype=float)
    F = factors[list(FACTOR_NAMES)].to_numpy(dtype=float)

    n = min(len(y), len(F))
    if n < 20:
        return {"available": False,
                "note": (f"Hacen falta al menos 20 periodos alineados y hay {n}: "
                         "con menos, el alfa no se distingue de nada.")}
    y, F = y[-n:], F[-n:]

    ok = np.isfinite(y) & np.isfinite(F).all(axis=1)
    y, F = y[ok], F[ok]
    if y.size < 20:
        return {"available": False,
                "note": f"Solo {y.size} periodos utilizables tras limpiar."}

    X = np.column_stack([np.ones(y.size), F])
    # Regla habitual para la ventana de Bartlett: ~4·(n/100)^(2/9).
    if lags is None:
        lags = max(1, int(np.floor(4 * (y.size / 100.0) ** (2.0 / 9.0))))

    beta, se, resid = _newey_west_ols(y, X, lags)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(se > 0, beta / se, 0.0)
    # Recorte: con residuos de 1e-17 los t salen de 1e14 y el informe deja de ser
    # creíble aunque sea correcto. Por encima del tope todos significan lo mismo.
    t = np.clip(np.nan_to_num(t, nan=0.0, posinf=T_STAT_CAP, neginf=-T_STAT_CAP),
                -T_STAT_CAP, T_STAT_CAP)

    sst = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - float(np.sum(resid ** 2)) / sst if sst > 0 else float("nan")
    degenerado = bool(np.isfinite(r2) and r2 >= DEGENERATE_R2)

    from scipy.stats import norm
    p_alpha = float(2.0 * norm.sf(abs(t[0])))
    significativa = bool(abs(t[0]) > 1.96)

    # Las DOS condiciones. La estadística sola tiene un modo degenerado: un ajuste
    # casi perfecto deja residuos minúsculos, el error estándar tiende a cero y el
    # t se dispara sobre un alfa que económicamente no existe.
    alfa_anual = float(beta[0]) * PERIODS_PER_YEAR
    relevante = bool(abs(alfa_anual) >= MIN_ECONOMIC_ALPHA_ANNUAL)
    tiene_alfa = significativa and relevante

    return {
        "available": True,
        "n_periods": int(y.size),
        "alpha": round(float(beta[0]), 6),
        "alpha_annualized_pct": round(alfa_anual * 100, 3),
        "alpha_t": round(float(t[0]), 3),
        "alpha_p": round(p_alpha, 5),
        "alpha_significant": significativa,
        "alpha_economically_relevant": relevante,
        "min_economic_alpha_annual_pct": MIN_ECONOMIC_ALPHA_ANNUAL * 100,
        "betas": {name: round(float(b), 4)
                  for name, b in zip(FACTOR_NAMES, beta[1:])},
        "beta_t": {name: round(float(tt), 2)
                   for name, tt in zip(FACTOR_NAMES, t[1:])},
        "r_squared": round(r2, 4) if np.isfinite(r2) else None,
        # Ajuste degenerado: la estrategia ES una combinación de los factores, los
        # residuos son numéricamente cero y ningún estadístico t de esta regresión
        # significa nada. Hay que decirlo, no solo recortar el número.
        "degenerate_fit": degenerado,
        "newey_west_lags": int(lags),
        "verdict": "ALFA" if tiene_alfa else "SIN_ALFA",
        "note": self_note(beta[0], alfa_anual, t[0], r2, significativa, relevante),
    }


def self_note(alpha: float, alfa_anual: float, t_alpha: float, r2: float,
              significativa: bool, relevante: bool) -> str:
    """El diagnóstico en palabras, que es lo que se lee de verdad."""
    explican = (f"El {r2:.0%} de su variación la explican los factores: lo que hace "
                "esta estrategia se consigue con exposición a mercado, tamaño y "
                "momento." if np.isfinite(r2) else "")

    if significativa and relevante:
        return (f"Alfa de {alfa_anual * 100:+.2f} % anual con t = {t_alpha:+.2f}: "
                "sobrevive al ajuste por los tres factores.")
    if significativa and not relevante:
        # El caso degenerado, dicho por su nombre.
        return (f"Alfa estadísticamente distinto de cero (t = {t_alpha:+.2f}) y "
                f"económicamente nulo: {alfa_anual * 100:+.2f} % anual. Es la firma "
                "de una estrategia que ES una combinación de los factores — el "
                f"ajuste es tan bueno que el error estándar se va a cero. {explican}")
    return (f"Alfa de {alfa_anual * 100:+.2f} % anual con t = {t_alpha:+.2f}, "
            f"indistinguible de cero. {explican}")
