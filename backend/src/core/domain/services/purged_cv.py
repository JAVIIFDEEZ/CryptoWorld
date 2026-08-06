"""
purged_cv.py — Validación cruzada con purga y embargo (López de Prado).

El problema, en una frase
─────────────────────────
`TimeSeriesSplit` respeta el orden temporal, y eso basta para creer que no hay
fuga. No basta.

Con un horizonte de 5 velas, la muestra del índice `k` tiene su etiqueta
definida por `close[k+5]`. Si el tramo de test empieza en `k+1`, entonces **las
últimas 5 filas del train contienen ya información del periodo de test**: su
etiqueta se resolvió mirando velas que el modelo no debería haber visto. El
orden temporal se ha respetado y la fuga está ahí igualmente.

No es la fuga masiva de predecir el pasado. Es una fuga pequeña, sistemática y
que siempre empuja en la misma dirección: **infla la precisión fuera de muestra
que se reporta**. Con horizonte 5 y tramos de 100 velas son 5 filas de cada 100
contaminadas — un 5 % de las muestras del train colindante, y son precisamente
las más parecidas a las de test.

Las dos correcciones, que no son la misma
─────────────────────────────────────────
· **Purga** — quitar del entrenamiento las muestras cuyo intervalo de etiqueta
  `[i, i+horizon]` solapa con el tramo de test. Es exacta y determinista: se
  sabe cuántas filas hay que quitar porque se sabe cuánto dura una etiqueta.

· **Embargo** — quitar además un margen de velas adicionales. No corrige un
  solapamiento de etiquetas sino la **correlación serial**: dos velas contiguas
  comparten régimen, volatilidad y microestructura aunque sus etiquetas no se
  toquen, y un modelo puede reconocer el tramo de test por su parecido con el
  final del train sin haber visto ninguna etiqueta suya.

Dónde cae el embargo en un esquema hacia delante
────────────────────────────────────────────────
En el k-fold de López de Prado el train puede estar DESPUÉS del test, y por eso
el embargo se aplica detrás del tramo de test. Aquí el esquema es de ventana
expansiva: el train siempre precede al test, así que no hay nada detrás que
embargar. El análogo que sí hace algo es aplicarlo **delante**, como separación
adicional entre el final del train y el inicio del test.

Se dice explícitamente porque la alternativa —copiar la fórmula del libro sin
mirar el esquema— daría un embargo que no elimina una sola fila y una sensación
de rigor sin rigor.

Capa de dominio: Python puro (numpy), sin sklearn ni Django.
"""

from __future__ import annotations

import math

import numpy as np

# Embargo por defecto, en fracción de la longitud total de la serie. El 1 %
# es el valor que usa López de Prado en los ejemplos del libro; con 2000 velas
# son 20 barras de separación adicional, por encima del horizonte.
DEFAULT_EMBARGO_PCT = 0.01


class PurgedTimeSeriesSplit:
    """
    Ventana expansiva con purga por horizonte de etiqueta y embargo.

    Compatible con la interfaz de `sklearn.model_selection.TimeSeriesSplit`
    (`n_splits`, `split(X)`, `get_n_splits`), así que sustituirlo es cambiar la
    línea de construcción y nada más.

    Diferencia con `TimeSeriesSplit`: entre el final del train y el inicio del
    test se abre un hueco de `horizon + embargo` velas que NO se usan para
    entrenar. Ese hueco es la corrección; el resto es idéntico.

    Un `horizon=0` y `embargo_pct=0` reproducen exactamente `TimeSeriesSplit`,
    lo que permite medir el efecto de la corrección comparando ambos sobre los
    mismos datos en vez de darlo por supuesto.
    """

    def __init__(self, n_splits: int = 5, horizon: int = 1,
                 embargo_pct: float = DEFAULT_EMBARGO_PCT) -> None:
        if n_splits < 2:
            raise ValueError("n_splits debe ser al menos 2.")
        self.n_splits = int(n_splits)
        self.horizon = max(0, int(horizon))
        self.embargo_pct = max(0.0, float(embargo_pct))

    def get_n_splits(self, X=None, y=None, groups=None) -> int:  # noqa: ARG002
        return self.n_splits

    def gap_for(self, n_samples: int) -> int:
        """Velas descartadas entre train y test: purga + embargo."""
        return self.horizon + int(math.ceil(self.embargo_pct * n_samples))

    def split(self, X, y=None, groups=None):  # noqa: ARG002
        """
        Genera `(train_idx, test_idx)` por tramo.

        Un tramo se OMITE si tras purgar no queda entrenamiento. Omitirlo es
        preferible a devolver un train vacío o a encoger el hueco: encogerlo
        sería reintroducir justo la fuga que este objeto existe para cerrar, y
        un tramo menos es un dato menos, no un dato mal medido.
        """
        n_samples = len(X)
        n_folds = self.n_splits + 1
        fold = n_samples // n_folds
        if fold < 1:
            raise ValueError(
                f"Serie demasiado corta ({n_samples}) para {self.n_splits} tramos.")

        gap = self.gap_for(n_samples)
        indices = np.arange(n_samples)
        for k in range(1, self.n_splits + 1):
            test_start = k * fold
            test_end = n_samples if k == self.n_splits else (k + 1) * fold
            train_end = test_start - gap
            if train_end <= 0:
                continue
            yield indices[:train_end], indices[test_start:test_end]


def purged_walk_forward(n_samples: int, n_splits: int, horizon: int,
                        embargo_pct: float = DEFAULT_EMBARGO_PCT) -> list[tuple]:
    """Los mismos tramos como lista de `(train_slice, test_slice)` en índices.

    Para código que no consume el protocolo de sklearn — el walk-forward del
    generador de estrategias, por ejemplo, que trabaja con `df.iloc[...]`.
    """
    splitter = PurgedTimeSeriesSplit(n_splits=n_splits, horizon=horizon,
                                     embargo_pct=embargo_pct)
    return [(tr, te) for tr, te in splitter.split(np.empty((n_samples, 1)))]


def leakage_report(n_samples: int, n_splits: int, horizon: int,
                   embargo_pct: float = DEFAULT_EMBARGO_PCT) -> dict:
    """
    Cuántas muestras retira la corrección, para poder decirlo en vez de
    afirmar que «ahora está purgado».

    Sin esta cifra, purgar es un cambio invisible: los números se mueven un poco
    y nadie sabe si es porque la corrección hizo algo o porque cambió la semilla.
    """
    splitter = PurgedTimeSeriesSplit(n_splits, horizon, embargo_pct)
    gap = splitter.gap_for(n_samples)
    folds = list(splitter.split(np.empty((n_samples, 1))))
    purged = sum(min(gap, k * (n_samples // (n_splits + 1))) for k in range(1, len(folds) + 1))
    return {
        "n_samples": n_samples,
        "n_splits_requested": n_splits,
        "n_splits_usable": len(folds),
        "horizon": horizon,
        "embargo_bars": gap - horizon,
        "gap_bars": gap,
        "train_samples_removed": purged,
        "note": (
            f"Entre el final de cada train y el inicio de su test se descartan {gap} "
            f"velas: {horizon} por solapamiento de etiquetas y {gap - horizon} de "
            "embargo por correlación serial."
        ),
    }
