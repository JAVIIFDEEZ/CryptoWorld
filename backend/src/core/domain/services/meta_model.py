"""
meta_model.py — Meta-modelo: de la señal a la convicción, y de ahí al tamaño.

Cierra el circuito que abrió `labeling.py`. El modelo primario —la señal técnica
compilada del spec— decide **dónde** entrar. El meta-modelo no repite esa
decisión: aprende **cuándo el primario acierta**, y su probabilidad se convierte
en el **tamaño** de la posición.

Por qué esto no es «otro modelo de predicción»
──────────────────────────────────────────────
Predecir la dirección del mercado es difícil y los clasificadores fracasan
haciéndolo. Predecir si una señal concreta va a funcionar es un problema mucho
más acotado: el primario ya ha filtrado el universo a un puñado de situaciones
con una estructura común, y sobre ese subconjunto hay regularidades aprendibles
(«este cruce falla cuando la volatilidad está en máximos»). Es la razón por la
que López de Prado separa dirección de tamaño.

Y trae una ventaja que la separación hace evidente: el meta-modelo **solo puede
reducir** la exposición, nunca invertir la señal. Un error suyo cuesta operar
menos de la cuenta, no operar al revés — un modo de fallo mucho más benigno.

Cuidados de rigor, todos deliberados
────────────────────────────────────
  · **Partición temporal, jamás aleatoria.** Un `train_test_split` mezclado
    entrena con el futuro y da precisiones espectaculares que no existen.
  · **Pesos por unicidad** de `labeling.average_uniqueness`: las etiquetas
    triple-barrera se solapan y no son observaciones independientes.
  · **Embargo entre train y test**: se descartan las muestras cuyo horizonte
    invade el tramo de evaluación. Aquí SÍ aplica el purging del libro, porque
    aquí sí se está entrenando un modelo — a diferencia del walk-forward del
    motor, donde el spec viene fijo.
  · Si no hay señal aprendible, se dice. Un meta-modelo que no supera al
    primario no debe usarse, y devolver `usable: False` es más útil que un
    número que aparenta convicción.

Capa de dominio: scikit-learn y NumPy, sin Django.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.domain.services import labeling


@dataclass(frozen=True)
class MetaModelConfig:
    """Presupuesto y rigor del meta-modelo."""
    test_fraction: float = 0.3    # tramo FINAL reservado para evaluar
    embargo_bars: int = 10        # muestras descartadas en la frontera train/test
    min_train_events: int = 40    # por debajo, no hay con qué aprender
    # El meta-modelo debe SUPERAR a operar siempre; si no, no aporta.
    min_edge_over_primary: float = 0.02
    seed: int = 42


def _prepare(features, labels: list[dict]) -> tuple:
    """Alinea features con eventos etiquetados y devuelve (X, índices)."""
    import pandas as pd

    X = pd.DataFrame(features).replace([np.inf, -np.inf], np.nan)
    rows, keep = [], []
    for k, lab in enumerate(labels):
        t0 = lab["t0"]
        if t0 >= len(X):
            continue
        row = X.iloc[t0]
        if row.isna().any():
            continue          # indicadores aún calentando: no se inventa el dato
        rows.append(row.to_numpy(dtype=float))
        keep.append(k)
    return (np.array(rows, dtype=float) if rows else np.empty((0, X.shape[1]))), keep


def train_meta_model(features, labels: list[dict], primary_side=None,
                     config: MetaModelConfig | None = None) -> dict:
    """
    Entrena el meta-modelo sobre las etiquetas triple-barrera.

    Devuelve el modelo entrenado, su rendimiento en el tramo reservado y —lo
    importante— si **aporta algo** sobre operar todas las señales del primario.
    `usable=False` significa que no hay señal aprendible aquí; usarlo igualmente
    solo añadiría ruido con apariencia de sofisticación.
    """
    from sklearn.ensemble import RandomForestClassifier

    cfg = config or MetaModelConfig()
    meta = labeling.meta_label(labels, primary_side)
    if meta.get("n", 0) == 0:
        return {"usable": False, "note": meta.get("note", "Sin eventos que aprender.")}

    X, keep = _prepare(features, labels)
    if X.shape[0] < cfg.min_train_events:
        return {"usable": False,
                "note": f"Solo {X.shape[0]} eventos con features completas: "
                        "insuficientes para entrenar un meta-modelo."}

    y = np.array([meta["y"][k] for k in keep], dtype=int)
    weights = np.array([meta["sample_weights"][k] for k in keep], dtype=float)
    t1 = np.array([labels[k]["t1"] for k in keep], dtype=int)
    t0 = np.array([labels[k]["t0"] for k in keep], dtype=int)

    # ── Partición TEMPORAL con embargo ────────────────────────────
    split = int(len(y) * (1.0 - cfg.test_fraction))
    if split < cfg.min_train_events or len(y) - split < 10:
        return {"usable": False,
                "note": "No hay tramo de evaluación suficiente tras la partición temporal."}

    test_start_bar = int(t0[split])
    # Purga: fuera del train las muestras cuyo horizonte invade el test.
    train_mask = np.zeros(len(y), dtype=bool)
    train_mask[:split] = True
    train_mask &= t1 < (test_start_bar - cfg.embargo_bars)

    if int(train_mask.sum()) < cfg.min_train_events:
        return {"usable": False,
                "note": "Tras purgar el solape entre train y test no quedan "
                        "muestras suficientes para entrenar."}

    if len(np.unique(y[train_mask])) < 2:
        return {"usable": False,
                "note": "El primario acierta (o falla) siempre en el tramo de "
                        "entrenamiento: no hay nada que discriminar."}

    model = RandomForestClassifier(
        n_estimators=200, max_depth=4, min_samples_leaf=10,
        class_weight="balanced", random_state=cfg.seed, n_jobs=1,
    )
    model.fit(X[train_mask], y[train_mask], sample_weight=weights[train_mask])

    X_test, y_test = X[split:], y[split:]
    proba = model.predict_proba(X_test)[:, 1]
    predicted = (proba >= 0.5).astype(int)

    accuracy = float((predicted == y_test).mean())
    # Línea base honesta: operar TODAS las señales del primario.
    baseline = float(y_test.mean())
    # Precisión cuando el meta-modelo dice que sí — la métrica que de verdad
    # importa, porque es la que decide dónde se pone el dinero.
    selected = y_test[predicted == 1]
    precision = float(selected.mean()) if selected.size else 0.0
    edge = precision - baseline

    return {
        "usable": bool(selected.size >= 5 and edge >= cfg.min_edge_over_primary),
        "model": model,
        "feature_names": list(getattr(features, "columns", [])),
        "n_events": int(len(y)),
        "n_train": int(train_mask.sum()),
        "n_test": int(len(y_test)),
        "accuracy": round(accuracy, 4),
        "primary_hit_rate": round(baseline, 4),
        "meta_precision": round(precision, 4),
        "edge_over_primary": round(edge, 4),
        "signals_taken_pct": round(float(predicted.mean() * 100), 1),
        "note": (
            f"El primario acierta el {baseline * 100:.0f}% de las veces. "
            f"Filtrando con el meta-modelo, el acierto sube al {precision * 100:.0f}% "
            f"operando solo el {predicted.mean() * 100:.0f}% de las señales."
            if selected.size and edge >= cfg.min_edge_over_primary else
            "El meta-modelo no mejora al primario de forma apreciable: no aporta "
            "y no debe usarse para dimensionar. Operar todas las señales es "
            "preferible a filtrar con ruido."
        ),
    }


def size_signals(model_result: dict, features, signal_indices: list[int],
                 max_fraction: float = 1.0, floor: float = 0.5) -> dict:
    """
    Tamaño por señal a partir de la convicción del meta-modelo.

    Si el meta-modelo no es utilizable, devuelve tamaño pleno en todas: es la
    degradación correcta — sin convicción medible, se opera como siempre en
    lugar de inventarse una modulación.
    """
    import pandas as pd

    if not model_result.get("usable"):
        return {
            "applied": False,
            "sizes": {int(i): max_fraction for i in signal_indices},
            "note": "Meta-modelo no utilizable: se opera con tamaño pleno.",
        }

    X = pd.DataFrame(features).replace([np.inf, -np.inf], np.nan)
    model = model_result["model"]
    sizes: dict[int, float] = {}
    probabilities: dict[int, float] = {}
    for i in signal_indices:
        i = int(i)
        if i >= len(X) or X.iloc[i].isna().any():
            sizes[i] = max_fraction          # sin features, no se penaliza
            continue
        p = float(model.predict_proba(X.iloc[[i]].to_numpy(dtype=float))[0, 1])
        probabilities[i] = round(p, 4)
        sizes[i] = labeling.bet_size(p, max_fraction=max_fraction, floor=floor)

    taken = sum(1 for s in sizes.values() if s > 0)
    return {
        "applied": True,
        "sizes": sizes,
        "probabilities": probabilities,
        "signals_total": len(sizes),
        "signals_taken": taken,
        "mean_size": round(float(np.mean(list(sizes.values()))), 4) if sizes else 0.0,
        "note": (
            f"{taken} de {len(sizes)} señales superan el suelo de convicción. "
            "El tamaño escala con la probabilidad de acierto: fuerte donde el "
            "sistema es fiable, nada donde no lo es."
        ),
    }
