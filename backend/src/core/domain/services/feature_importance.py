"""
feature_importance.py — Importancia que sobrevive fuera de muestra.

El problema con el número que el producto lleva mostrando
────────────────────────────────────────────────────────
`RandomForestClassifier.feature_importances_` es **MDI**: impureza media
decrecida, acumulada mientras el árbol se construye. Es lo que casi todo el
mundo enseña como «variables más influyentes», y tiene dos defectos que la hacen
inservible para afirmar nada sobre capacidad predictiva:

  · **Es dentro de muestra.** Una variable puede reducir impureza en el
    entrenamiento memorizando ruido y no aportar absolutamente nada fuera. MDI
    no distingue esos dos casos: los premia igual.
  · **Está sesgada por cardinalidad.** Una variable continua con muchos valores
    distintos ofrece más puntos de corte y sube por construcción. Entre 17
    features técnicas —todas continuas, con escalas y granularidades muy
    distintas— eso ordena la lista por forma de la variable, no por información.

**MDA** (Mean Decrease Accuracy) mide otra cosa: se permuta una columna en el
tramo de TEST y se observa cuánto cae la precisión FUERA de muestra. Si la
columna no informaba, romperla no cuesta nada. Es una pregunta sobre predicción,
no sobre cómo se construyó el árbol.

Se permuta solo el test, nunca el train: permutar el train mediría cuánto empeora
el modelo al entrenarlo peor, que es otra pregunta.

El efecto sustitución, que invalida el resultado si se ignora
────────────────────────────────────────────────────────────
Con variables correlacionadas, el MDA individual reparte la importancia entre
ellas y las hunde todas. Si `rsi_14` y `rsi_7` dicen casi lo mismo, permutar una
apenas mueve la precisión porque la otra la sustituye, y las dos parecen
inútiles cuando juntas sí informan. En un conjunto de 17 indicadores técnicos
—que es un conjunto de sinónimos, no de variables independientes— ignorarlo no
es un matiz: es la diferencia entre una lista de importancias y una lista de
ceros.

Por eso se mide **por CLÚSTER**: se agrupan las columnas por correlación y se
permuta el grupo entero.

Por qué cada importancia lleva su error estándar
────────────────────────────────────────────────
Una caída media de 0,01 con desviación 0,05 no es importancia, es ruido. Sin la
incertidumbre al lado, una lista ordenada siempre parece significativa: SIEMPRE
hay un primero, tenga o no señal. El error estándar se calcula **entre tramos**,
no entre permutaciones: las permutaciones de un mismo tramo comparten modelo y
comparten test, así que solo miden la varianza del sorteo. Contarlas como
independientes estrecha el intervalo por √N y fabrica significancia.

Y como se contrasta un clúster por cada grupo, se corrige por multiplicidad
(Benjamini-Hochberg): con ocho grupos y ningún efecto real, la probabilidad de
que alguno salga «significativo» al 5 % es del 34 %, no del 5 %.

Capa de dominio: numpy puro, sin sklearn ni Django. El modelo entra ya ajustado
y solo se le piden predicciones, así que sirve para cualquier clasificador con
`predict`.
"""

from __future__ import annotations

import numpy as np

from core.domain.services import significance as sig

# Umbral de correlación absoluta para considerar que dos columnas dicen lo
# mismo. Es el mismo listón que el filtro de decorrelación del libro de
# estrategias: por debajo de 0,7 dos series todavía aportan variación propia.
CLUSTER_THRESHOLD = 0.7

# Permutaciones por tramo y clúster. Tres bastan: promedian el sorteo dentro del
# tramo, que es para lo único que sirven — la incertidumbre que se reporta sale
# de la variación ENTRE tramos, y subir este número no la reduce.
DEFAULT_PERMUTATIONS = 3

# Tasa de falso descubrimiento admitida sobre la familia de clústeres.
DEFAULT_FDR = 0.10


def _pairwise_abs_corr(X: np.ndarray) -> np.ndarray:
    """
    Correlación absoluta entre columnas, par a par y sobre filas completas.

    `np.corrcoef` propaga: un solo NaN en una columna deja TODA su fila de
    correlaciones en NaN, y esa columna nunca se agruparía con nadie — quedaría
    como grupo propio y su importancia se mediría sin las hermanas que la
    sustituyen, que es el error que el agrupamiento existe para evitar.

    Aquí cada par se calcula con las filas en que ambas columnas son finitas,
    que es lo que hace `DataFrame.corr()`. Un par sin solape suficiente vale 0:
    no hay evidencia de que digan lo mismo.
    """
    p = X.shape[1]
    out = np.eye(p)
    for i in range(p):
        for j in range(i + 1, p):
            ok = np.isfinite(X[:, i]) & np.isfinite(X[:, j])
            if ok.sum() < 3:
                continue
            a, b = X[ok, i], X[ok, j]
            sa, sb = a.std(), b.std()
            if sa <= 0 or sb <= 0:
                continue          # una constante no correlaciona con nada
            r = float(np.mean((a - a.mean()) * (b - b.mean())) / (sa * sb))
            out[i, j] = out[j, i] = abs(r) if np.isfinite(r) else 0.0
    return out


def cluster_columns(values, threshold: float = CLUSTER_THRESHOLD) -> list[list[int]]:
    """
    Agrupa columnas que dicen casi lo mismo, por correlación absoluta.

    Aglomeración voraz de un solo enlace: se recorre en orden y cada columna se
    une al primer grupo con el que supere el umbral. No es clustering jerárquico
    completo y no hace falta que lo sea — lo que se necesita es que ningún par
    fuertemente correlacionado quede en grupos distintos, y eso lo garantiza.

    Devuelve índices de columna, no nombres, para que el llamante decida cómo
    etiquetarlos.
    """
    X = np.asarray(values, dtype=float)
    if X.ndim != 2 or X.shape[1] == 0:
        return []
    if X.shape[1] == 1:
        return [[0]]

    corr = _pairwise_abs_corr(X)

    clusters: list[list[int]] = []
    for j in range(X.shape[1]):
        for group in clusters:
            if any(corr[j, other] >= threshold for other in group):
                group.append(j)
                break
        else:
            clusters.append([j])
    return clusters


def permutation_drops(model, X_test, y_test, clusters: list[list[int]],
                      n_permutations: int = DEFAULT_PERMUTATIONS,
                      seed: int = 42) -> np.ndarray:
    """
    Caída de precisión al romper cada clúster, en UN tramo de test.

    El modelo entra ya ajustado con el train de ese tramo; aquí solo se le piden
    predicciones. Devuelve un vector con una caída por clúster: positivo
    significa que romper esa información empeora el acierto.

    Las columnas de un clúster se permutan **con la misma permutación**, no cada
    una por su lado. Barajarlas independientemente destruiría también la
    correlación entre ellas, que no es lo que se quiere medir: se quiere romper
    su relación con el objetivo dejando intacta su estructura interna.
    """
    X = np.asarray(X_test, dtype=float)
    y = np.asarray(y_test)
    if X.shape[0] == 0 or not clusters:
        return np.zeros(len(clusters))

    base = float(np.mean(model.predict(X) == y))
    rng = np.random.default_rng(seed)
    out = np.zeros(len(clusters))
    for c, cols in enumerate(clusters):
        caidas = []
        for _ in range(max(1, n_permutations)):
            roto = X.copy()
            orden = rng.permutation(X.shape[0])
            for j in cols:
                roto[:, j] = X[orden, j]
            caidas.append(base - float(np.mean(model.predict(roto) == y)))
        out[c] = float(np.mean(caidas))
    return out


def aggregate_clusters(names: list[str], clusters: list[list[int]], fold_drops,
                       fdr: float = DEFAULT_FDR) -> list[dict]:
    """
    Une las caídas de todos los tramos en una importancia con incertidumbre.

    `fold_drops` es una matriz `(n_tramos, n_clústeres)`. Para cada clúster:
    media entre tramos, error estándar entre tramos, y un contraste de una cola
    —¿es la caída mayor que cero?— corregido por multiplicidad.

    Con un solo tramo no hay error estándar posible y nada sale significativo.
    Es el resultado correcto: una única medición no permite distinguir señal de
    sorteo, y devolver un número sin incertidumbre invitaría a leerlo como si sí.
    """
    drops = np.asarray(fold_drops, dtype=float)
    if drops.ndim != 2 or drops.size == 0:
        return []

    n_folds = drops.shape[0]
    medias = drops.mean(axis=0)
    if n_folds > 1:
        errores = drops.std(axis=0, ddof=1) / np.sqrt(n_folds)
    else:
        errores = np.full(len(clusters), np.nan)

    from scipy.stats import t as _t

    p_valores = []
    for media, error in zip(medias, errores):
        if not np.isfinite(error) or error <= 0:
            # Error nulo con media positiva es el caso degenerado de tramos
            # idénticos: no hay evidencia de dispersión, tampoco de señal.
            p_valores.append(1.0)
            continue
        # Una cola: la pregunta es si la caída es MAYOR que cero. Que romper un
        # grupo mejore el acierto es información, pero no es importancia.
        p_valores.append(float(_t.sf(media / error, df=n_folds - 1)))

    corregidos = sig.benjamini_hochberg(p_valores, fdr=fdr)["results"]

    filas = []
    for c, cols in enumerate(clusters):
        etiqueta = names[cols[0]] if cols else "?"
        filas.append({
            "feature": etiqueta,
            "columns": [names[j] for j in cols],
            "importance": round(float(medias[c]), 5),
            "std_error": round(float(errores[c]), 5) if np.isfinite(errores[c]) else None,
            "p_value": round(float(p_valores[c]), 5),
            "significant": bool(corregidos[c]["significant"]),
        })
    filas.sort(key=lambda f: f["importance"], reverse=True)
    return filas
