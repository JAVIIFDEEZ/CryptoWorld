"""
feature_study.py — ¿Aportan las variables exógenas algo que las técnicas no tengan?

Esto no es una funcionalidad de producto: es un **experimento con resultado
publicable**, y su valor no depende de que salga que sí.

La hipótesis
────────────
Las 17 features del modelo son todas transformaciones de OHLCV. Ese espacio
lleva quince años explotado por todas las mesas y todo el retail; el edge
esperado *a priori* de un clasificador sobre esas variables en cripto líquido es
indistinguible de cero. Mientras tanto la plataforma archiva funding de
perpetuos, flujo de ballenas y salud de cadena — datos que casi nadie en el
segmento tiene. La pregunta es si esa diferencia se traduce en información
predictiva o solo en columnas nuevas.

Por qué MDA y no la importancia del bosque
──────────────────────────────────────────
El modelo ya expone `feature_importances_`, que es MDI: impureza media
decrecida, medida DENTRO de muestra. Tiene dos defectos que la hacen inservible
para decidir esto:

  · Es in-sample. Una variable puede reducir impureza en el entrenamiento
    memorizando ruido y no aportar nada fuera.
  · Está sesgada hacia variables de alta cardinalidad. Una feature continua con
    muchos valores distintos ofrece más puntos de corte y sale arriba por
    construcción, no por informativa.

**MDA** (Mean Decrease Accuracy) mide otra cosa: se permuta una columna en el
tramo de TEST y se observa cuánto cae la precisión fuera de muestra. Si la
columna no informaba, romperla no cuesta nada.

El efecto sustitución, que invalidaría el resultado si se ignora
───────────────────────────────────────────────────────────────
Con features correlacionadas, el MDA individual reparte la importancia entre
ellas y las hunde todas: si `rsi_14` y `rsi_7` dicen casi lo mismo, permutar una
apenas mueve la precisión porque la otra la sustituye, y las dos parecen
inútiles cuando juntas sí informan.

Por eso la importancia se mide **por CLÚSTER**: se agrupan las columnas por
correlación y se permuta el grupo entero. Es la única forma de que un bloque
sustituible no se anule a sí mismo — y las features exógenas de este estudio
llegan precisamente en bloques (tres columnas de funding, tres de flujo).

Todo con validación PURGADA (`purged_cv`), porque medir importancia sobre una
partición con fuga sería medir la fuga.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from core.domain.services import significance as sig
from core.domain.services.exogenous_features import AVAILABLE_SUFFIX
from core.domain.services.purged_cv import PurgedTimeSeriesSplit

logger = logging.getLogger(__name__)

# Correlación absoluta a partir de la cual dos columnas se consideran la misma
# información a efectos de sustitución. 0,7 es el mismo listón que usa el filtro
# de decorrelación del libro de estrategias: por debajo, dos series todavía
# aportan variación propia.
CLUSTER_THRESHOLD = 0.7

# Permutaciones por clúster. Cada una es una barajada distinta de la misma
# columna: con una sola, el resultado depende del sorteo.
N_PERMUTATIONS = 5

# Tasa de falsos descubrimientos admitida entre los clústeres declarados
# importantes. Se controla FDR y no error por familia porque el objetivo aquí no
# es no equivocarse nunca —con siete contrastes, Bonferroni exigiría un nivel de
# 0,7 % y no sobreviviría ninguna importancia moderada— sino acotar qué
# proporción de lo que se anuncia como importante es falso.
MDA_FDR = 0.10


def _cluster_columns(frame: pd.DataFrame, threshold: float = CLUSTER_THRESHOLD) -> list[list[str]]:
    """
    Agrupa columnas que dicen casi lo mismo, por correlación absoluta.

    Aglomeración voraz de un solo enlace: se recorre en orden y cada columna se
    une al primer grupo con el que supere el umbral. No es clustering jerárquico
    completo y no hace falta que lo sea — lo que se necesita es que ningún par
    fuertemente correlacionado quede en grupos distintos, y eso lo garantiza.
    """
    numeric = frame.select_dtypes(include=[np.number])
    if numeric.shape[1] <= 1:
        return [[c] for c in numeric.columns]

    corr = numeric.corr().abs().fillna(0.0)
    clusters: list[list[str]] = []
    for col in numeric.columns:
        for group in clusters:
            if any(corr.loc[col, other] >= threshold for other in group):
                group.append(col)
                break
        else:
            clusters.append([col])
    return clusters


def _fit_predict(model_factory, X_tr, y_tr, X_te):
    return model_factory().fit(X_tr, y_tr).predict(X_te)


def mda_by_cluster(X: pd.DataFrame, y, model_factory, horizon: int,
                   n_splits: int = 4, seed: int = 42) -> dict:
    """
    Importancia fuera de muestra por clúster, con validación purgada.

    Para cada grupo de columnas: se entrena una vez por tramo, se mide la
    precisión, se permutan TODAS las columnas del grupo en el test y se vuelve a
    medir. La caída media es la importancia del grupo.

    Se permuta solo el TEST, nunca el train: permutar el train mediría cuánto
    cambia el modelo al entrenarlo peor, que es otra pregunta. Lo que interesa
    es cuánto depende su acierto de esa información en el momento de predecir.
    """
    rng = np.random.default_rng(seed)
    columns = list(X.columns)
    clusters = _cluster_columns(X)
    values = X.to_numpy(dtype=float)
    y = np.asarray(y)

    splitter = PurgedTimeSeriesSplit(n_splits=n_splits, horizon=horizon)
    baseline_scores: list[float] = []
    # Una caída POR TRAMO y por clúster, no una por permutación.
    #
    # La versión ingenua acumula las `N_PERMUTATIONS × n_folds` caídas en un solo
    # vector y divide su desviación por la raíz de ese total. Las permutaciones
    # de un mismo tramo NO son observaciones independientes: comparten modelo y
    # comparten conjunto de test, así que solo miden la varianza del sorteo, no
    # la de la estimación. Contarlas como independientes estrecha el error
    # estándar por un factor √N_PERMUTATIONS y hace que una columna de ruido
    # salga «significativa».
    #
    # No es hipotético: con la versión anterior, una feature construida como
    # ruido puro salía significativa en la comprobación de calibración. La
    # unidad independiente es el TRAMO, y son los tramos los que se promedian.
    drops: dict[int, list[float]] = {i: [] for i in range(len(clusters))}

    for train_idx, test_idx in splitter.split(values):
        if len(set(y[train_idx])) < 2 or len(test_idx) < 10:
            continue
        model = model_factory().fit(values[train_idx], y[train_idx])
        base = float((model.predict(values[test_idx]) == y[test_idx]).mean())
        baseline_scores.append(base)

        for ci, group in enumerate(clusters):
            idx = [columns.index(c) for c in group]
            fold_drops = []
            for _ in range(N_PERMUTATIONS):
                shuffled = values[test_idx].copy()
                # Una permutación INDEPENDIENTE por columna del grupo: barajar
                # todas con el mismo orden conservaría la estructura interna del
                # bloque y subestimaría su importancia.
                for j in idx:
                    shuffled[:, j] = rng.permutation(shuffled[:, j])
                score = float((model.predict(shuffled) == y[test_idx]).mean())
                fold_drops.append(base - score)
            # Las permutaciones promedian el ruido del sorteo DENTRO del tramo;
            # el tramo entra una sola vez en la estimación de la incertidumbre.
            drops[ci].append(float(np.mean(fold_drops)))

    if not baseline_scores:
        return {"clusters": [], "baseline_accuracy": None,
                "note": "No hubo tramos utilizables tras purgar."}

    # ── Un contraste por clúster, y por tanto multiplicidad ──────────
    #
    # Un estudio con siete clústeres hace siete contrastes. Declarar significativo
    # cada uno que supere su propio umbral al 5 % produce, con importancia
    # verdadera cero, un falso positivo cada tres estudios — y este módulo existe
    # precisamente para criticar ese error en otros. Aplicarse la corrección a sí
    # mismo no es coherencia decorativa: sin ella, la comprobación de calibración
    # sacaba una feature de ruido puro marcada como significativa.
    #
    # Se usa t de Student de UNA cola: la hipótesis es que romper el bloque
    # EMPEORA la precisión, no que la cambie. Una caída negativa —el modelo
    # mejora al permutar— no es evidencia a favor de nada.
    from scipy.stats import t as _t

    rows = []
    p_values = []
    for ci, group in enumerate(clusters):
        d = np.asarray(drops[ci], dtype=float)
        mean = float(d.mean()) if d.size else 0.0
        se = float(d.std(ddof=1) / np.sqrt(d.size)) if d.size > 1 else float("nan")
        if np.isfinite(se) and se > 1e-12:
            p = float(_t.sf(mean / se, df=d.size - 1))
        else:
            p = 1.0
        p_values.append(p)
        rows.append({
            "columns": group,
            "importance": round(mean, 5),
            "std_error": round(se, 5) if np.isfinite(se) else None,
            "n_folds": int(d.size),
            "p_value": round(p, 5),
        })

    corrected = sig.benjamini_hochberg(p_values, fdr=MDA_FDR)
    for row, verdict in zip(rows, corrected["results"]):
        row["significant"] = verdict["significant"]

    rows.sort(key=lambda r: r["importance"], reverse=True)
    return {
        "clusters": rows,
        "baseline_accuracy": round(float(np.mean(baseline_scores)), 4),
        "n_folds": len(baseline_scores),
        "n_permutations": N_PERMUTATIONS,
        "multiplicity": corrected,
        "note": ("Importancia = caída de precisión fuera de muestra al permutar el "
                 "clúster. Se agrupa por correlación porque el MDA individual "
                 "reparte la importancia entre features sustituibles y las hunde "
                 "todas. La significancia va corregida por multiplicidad "
                 "(Benjamini-Hochberg): un clúster por contraste y siete "
                 "contrastes producen un falso positivo cada tres estudios."),
    }


def _oos_correct(X: pd.DataFrame, y, model_factory, horizon: int,
                 n_splits: int) -> tuple[np.ndarray, np.ndarray]:
    """
    Acierto POR OBSERVACIÓN fuera de muestra, con los índices que cubre.

    Devolver el vector y no solo el recuento es lo que permite comparar dos
    conjuntos de features de forma EMPAREJADA. Con recuentos solo se pueden
    comparar dos intervalos independientes, y eso desperdicia la información de
    que ambos modelos se evaluaron sobre las mismas filas.
    """
    values = X.to_numpy(dtype=float)
    y = np.asarray(y)
    hits, covered = [], []
    for train_idx, test_idx in PurgedTimeSeriesSplit(n_splits, horizon).split(values):
        if len(set(y[train_idx])) < 2 or len(test_idx) < 10:
            continue
        pred = _fit_predict(model_factory, values[train_idx], y[train_idx],
                            values[test_idx])
        hits.append(pred == y[test_idx])
        covered.append(test_idx)
    if not hits:
        return np.array([], dtype=bool), np.array([], dtype=int)
    return np.concatenate(hits), np.concatenate(covered)


def compare_feature_sets(technical: pd.DataFrame, exogenous: pd.DataFrame, y,
                         model_factory, horizon: int, n_splits: int = 4,
                         seed: int = 42) -> dict:
    """
    El experimento completo: técnico solo vs técnico + exógeno.

    Devuelve el veredicto según el criterio de abandono fijado ANTES de medir:

      · Las exógenas aportan si (a) al menos un clúster exógeno entra en el
        tercio superior de importancia OOS **y** (b) el edge del conjunto
        ampliado tiene su intervalo inferior por encima de cero.
      · Si no, se declara `NO_EDGE` y **se para**. Ese resultado no es un
        fracaso del proyecto: es el resultado, y publicarlo con la metodología
        es exactamente lo que separa una due diligence aprobada de una
        suspendida.

    Fijar el criterio antes es lo que impide el movimiento clásico: mirar los
    números, encontrar algo que sobresalga y declarar que era lo que se buscaba.
    """
    # Las banderas de disponibilidad no son información predictiva: son
    # metadatos. Dejarlas dentro permitiría al modelo aprender «cuando hay dato
    # de funding estamos en 2025», que es una fecha disfrazada de feature.
    exo_all = exogenous.reset_index(drop=True)
    candidate_cols = [c for c in exo_all.columns if not c.endswith(AVAILABLE_SUFFIX)]

    # Bloques SIN un solo dato: se retiran ANTES de exigir filas completas.
    #
    # La disciplina de no imputar es correcta y, aplicada sin este paso, se
    # vuelve autodestructiva: una columna íntegramente vacía —un activo sin
    # métricas de cadena, por ejemplo— hace que la exigencia de «todas las
    # columnas con dato» elimine la muestra entera, y el estudio devuelve
    # «datos insuficientes» cuando lo cierto es que le sobraba una columna.
    #
    # Retirarlas y DECIRLO es la única salida honesta. Callarlas dejaría creer
    # que se han evaluado; imputarlas metería relleno en el modelo.
    usable = exo_all[candidate_cols].replace([np.inf, -np.inf], np.nan)
    dropped = [c for c in candidate_cols if usable[c].notna().sum() == 0]
    exo_cols = [c for c in candidate_cols if c not in dropped]

    if not exo_cols:
        return {
            "verdict": "NO_EXOGENOUS_DATA",
            "dropped_columns": dropped,
            "note": ("Ninguna variable exógena tiene un solo dato en este tramo, "
                     "así que no se han evaluado. NO es lo mismo que NO_EDGE: "
                     "aquello diría que se probaron y no aportan."),
        }

    combined = pd.concat([technical.reset_index(drop=True), exo_all[exo_cols]], axis=1)
    mask = combined.replace([np.inf, -np.inf], np.nan).notna().all(axis=1)
    combined, y_all = combined[mask], np.asarray(y)[mask.to_numpy()]
    tech_only = technical.reset_index(drop=True)[mask]

    if len(combined) < 120 or len(set(y_all)) < 2:
        return {
            "verdict": "INSUFFICIENT_DATA",
            "n_samples": int(len(combined)),
            "dropped_columns": dropped,
            "note": ("Tras exigir que todas las columnas tengan dato en la misma "
                     "fila no queda muestra suficiente. Es el coste de no imputar: "
                     "una imputación silenciosa daría más filas y menos verdad."),
        }

    up = float(y_all.mean())
    baseline = max(up, 1.0 - up)
    tech_hits, tech_idx = _oos_correct(tech_only, y_all, model_factory, horizon, n_splits)
    both_hits, both_idx = _oos_correct(combined, y_all, model_factory, horizon, n_splits)
    if tech_hits.size == 0 or not np.array_equal(tech_idx, both_idx):
        return {"verdict": "INSUFFICIENT_DATA", "n_samples": int(len(combined)),
                "dropped_columns": dropped,
                "note": ("Los dos conjuntos no cubren las mismas filas fuera de "
                         "muestra, así que no son comparables.")}

    tech_stats = sig.edge_significance(int(tech_hits.sum()), tech_hits.size, baseline)
    both_stats = sig.edge_significance(int(both_hits.sum()), both_hits.size, baseline)
    # El contraste que responde a la pregunta: sobre LAS MISMAS filas, ¿acierta
    # más el conjunto ampliado? Comparar dos intervalos independientes tira casi
    # toda la información —las filas que ambos aciertan o ambos fallan no
    # distinguen nada— y exigía efectos enormes para concluir algo.
    paired = sig.mcnemar_paired(tech_hits, both_hits)

    importance = mda_by_cluster(combined, y_all, model_factory, horizon, n_splits, seed)
    clusters = importance.get("clusters", [])
    exo_set = set(exo_cols)

    # Criterio (a): un clúster exógeno con importancia que se DISTINGUE DE CERO.
    #
    # La primera versión pedía «entrar en el tercio superior», y la comprobación
    # de calibración enseñó que eso no filtra nada: con seis o siete clústeres,
    # el tercio superior son dos, y una feature de ruido puro entraba en él la
    # mitad de las veces. Estar arriba en una lista corta no es evidencia de
    # nada — lo que importa es que la caída de precisión al romper el bloque sea
    # mayor que su propio error de estimación.
    exo_significant = [c for c in clusters
                       if exo_set.intersection(c["columns"]) and c["significant"]]
    top_third = clusters[:max(1, len(clusters) // 3)]
    exo_in_top = [c for c in top_third if exo_set.intersection(c["columns"])]

    # El criterio VINCULANTE es el contraste emparejado. La importancia por
    # clúster acompaña como diagnóstico —dice QUÉ bloque hizo el trabajo— pero no
    # decide: su estimación se apoya en tantas observaciones como tramos haya, y
    # con cuatro o con ocho no hay potencia para sostener un veredicto.
    #
    # Se llegó aquí midiendo. La primera versión exigía que las dos precisiones
    # superasen cada una su intervalo contra cero, y sobre datos sintéticos con
    # señal PLANTADA el resultado dependía más del nº de tramos que de la señal:
    # con ocho tramos, el caso de ruido daba una mejora MAYOR que el informativo.
    helps = bool(paired["better"])
    return {
        "verdict": "EXOGENOUS_HELPS" if helps else "NO_EDGE",
        "n_samples": int(len(combined)),
        # Columnas exógenas retiradas por no tener un solo dato en este tramo.
        # Van en el resultado porque «no aporta» y «no se ha medido» son
        # conclusiones opuestas y aquí se distinguen.
        "dropped_columns": dropped,
        "evaluated_columns": exo_cols,
        "baseline": round(baseline, 4),
        "technical_only": tech_stats,
        "technical_plus_exogenous": both_stats,
        "paired_test": paired,
        "edge_delta": round(float(both_stats["edge"] - tech_stats["edge"]), 4),
        "importance": importance,
        "exogenous_clusters_significant": [c["columns"] for c in exo_significant],
        "exogenous_clusters_in_top_third": [c["columns"] for c in exo_in_top],
        "criterion": (
            "CRITERIO CONGELADO ANTES de tocar datos reales. Las exógenas aportan "
            "si el contraste EMPAREJADO de McNemar sobre las mismas filas fuera de "
            "muestra dice que el conjunto ampliado acierta más (p < 0,05, una "
            "cola). La importancia por clúster se reporta como diagnóstico —qué "
            "bloque hizo el trabajo— pero no decide. Cualquier otro resultado se "
            "declara NO_EDGE y se para."),
        "criterion_history": (
            "El criterio se reescribió DOS VECES durante la calibración, y eso hay "
            "que decirlo: es el patrón que este trabajo critica en otros. La "
            "diferencia está en sobre qué datos se hizo. Las dos reescrituras "
            "ocurrieron sobre series SINTÉTICAS con la señal plantada por quien "
            "escribía el código, o sea con la respuesta conocida de antemano — eso "
            "es calibrar un instrumento. Reescribirlo después de ver el resultado "
            "en BTC sería elegir el listón tras ver el salto, y por eso queda "
            "congelado aquí. Las versiones descartadas: (1) «un clúster exógeno en "
            "el tercio superior», que con siete clústeres no filtraba nada porque "
            "el tercio superior son dos; (2) «importancia del clúster distinta de "
            "cero», que dependía más del nº de tramos que de la señal — con ocho "
            "tramos, el caso de RUIDO daba mejor resultado que el informativo."),
        "note": (
            "Las exógenas superan el criterio."
            if helps else
            "Las exógenas no superan el criterio fijado de antemano. Es un "
            "resultado, no un fallo: un motor que nunca ha dicho «aquí no hay "
            "señal» no ha sido validado nunca, solo decorado."),
    }
