"""
test_purged_cv.py — La fuga que «respetar el orden temporal» no cierra.

`TimeSeriesSplit` entrena en el pasado y valida en el futuro, y por eso es fácil
darlo por bueno. No lo es. Con horizonte `h`, la etiqueta de la fila `k` se
resuelve mirando `close[k+h]`: si el test empieza en `k+1`, las últimas `h` filas
del train ya contienen información del periodo de test. El orden se ha respetado
y la fuga está ahí igualmente.

No es la fuga escandalosa de predecir el pasado. Es pequeña, sistemática, y
siempre empuja en el mismo sentido: **infla la precisión fuera de muestra que se
publica**. Estos tests fijan que el hueco existe, que tiene el tamaño correcto y
que las dos correcciones —purga y embargo— hacen cosas distintas.
"""

import numpy as np
import pytest

from core.domain.services.purged_cv import (
    DEFAULT_EMBARGO_PCT, PurgedTimeSeriesSplit, leakage_report, purged_walk_forward,
)


def _X(n=1000):
    return np.arange(n).reshape(-1, 1)


class TestTheGap:

    @pytest.mark.unit
    def test_no_training_label_reaches_into_the_test(self):
        """La propiedad de fondo. Si alguna fila de train tuviera su etiqueta
        dentro del test, el modelo estaría entrenando con el futuro que luego se
        le pide predecir."""
        horizon = 5
        splitter = PurgedTimeSeriesSplit(n_splits=4, horizon=horizon, embargo_pct=0.0)
        for train, test in splitter.split(_X()):
            assert train[-1] + horizon < test[0]

    @pytest.mark.unit
    def test_the_gap_is_purge_plus_embargo(self):
        n, horizon = 1000, 5
        splitter = PurgedTimeSeriesSplit(n_splits=4, horizon=horizon, embargo_pct=0.01)
        expected = horizon + 10          # 1 % de 1000
        for train, test in splitter.split(_X(n)):
            assert test[0] - train[-1] - 1 == expected

    @pytest.mark.unit
    def test_a_longer_horizon_opens_a_wider_gap(self):
        """El hueco de purga no es una constante: sale de cuánto dura la
        etiqueta. Un horizonte de 20 contamina cuatro veces más filas que uno
        de 5, y el hueco tiene que seguirlo."""
        gaps = []
        for horizon in (1, 5, 20):
            s = PurgedTimeSeriesSplit(n_splits=4, horizon=horizon, embargo_pct=0.0)
            train, test = next(iter(s.split(_X())))
            gaps.append(test[0] - train[-1] - 1)
        assert gaps == [1, 5, 20]

    @pytest.mark.unit
    def test_the_embargo_scales_with_the_series_not_the_horizon(self):
        """Purga y embargo corrigen cosas distintas: la primera, solapamiento de
        etiquetas; el segundo, correlación serial. Si el embargo dependiera del
        horizonte sería otra purga con otro nombre."""
        a = PurgedTimeSeriesSplit(n_splits=4, horizon=5, embargo_pct=0.02).gap_for(1000)
        b = PurgedTimeSeriesSplit(n_splits=4, horizon=5, embargo_pct=0.02).gap_for(4000)
        assert b - a == 60               # 2 % de 4000 menos 2 % de 1000


class TestEquivalence:

    @pytest.mark.unit
    def test_with_no_horizon_and_no_embargo_it_is_the_plain_split(self):
        """Permite MEDIR el efecto de la corrección comparando los dos sobre los
        mismos datos, en vez de darlo por supuesto."""
        from sklearn.model_selection import TimeSeriesSplit

        plain = list(TimeSeriesSplit(n_splits=4).split(_X()))
        purged = list(PurgedTimeSeriesSplit(n_splits=4, horizon=0,
                                            embargo_pct=0.0).split(_X()))
        assert len(plain) == len(purged)
        for (tr_a, te_a), (tr_b, te_b) in zip(plain, purged):
            assert np.array_equal(te_a, te_b)
            assert np.array_equal(tr_a, tr_b)

    @pytest.mark.unit
    def test_purging_only_ever_removes_training_data(self):
        """El test no se toca: si se moviera, los dos esquemas no serían
        comparables y la diferencia de precisión no significaría nada."""
        from sklearn.model_selection import TimeSeriesSplit

        plain = list(TimeSeriesSplit(n_splits=4).split(_X()))
        purged = list(PurgedTimeSeriesSplit(n_splits=4, horizon=10).split(_X()))
        for (tr_a, te_a), (tr_b, te_b) in zip(plain, purged):
            assert np.array_equal(te_a, te_b)
            assert len(tr_b) < len(tr_a)


class TestDegenerateCases:

    @pytest.mark.unit
    def test_a_fold_with_nothing_left_to_train_on_is_skipped(self):
        """Encoger el hueco para salvar el tramo sería reintroducir justo la fuga
        que esto cierra. Un tramo menos es un dato menos, no un dato mal
        medido."""
        splitter = PurgedTimeSeriesSplit(n_splits=4, horizon=400, embargo_pct=0.0)
        folds = list(splitter.split(_X(1000)))
        assert len(folds) < 4
        assert all(len(train) > 0 for train, _ in folds)

    @pytest.mark.unit
    def test_a_series_too_short_says_so(self):
        with pytest.raises(ValueError):
            list(PurgedTimeSeriesSplit(n_splits=10, horizon=1).split(_X(5)))

    @pytest.mark.unit
    def test_one_split_makes_no_sense(self):
        with pytest.raises(ValueError):
            PurgedTimeSeriesSplit(n_splits=1)

    @pytest.mark.unit
    def test_it_speaks_the_sklearn_protocol(self):
        """Sustituir `TimeSeriesSplit` tiene que ser cambiar una línea."""
        s = PurgedTimeSeriesSplit(n_splits=3, horizon=2)
        assert s.get_n_splits() == 3
        assert len(list(s.split(_X()))) == 3


class TestReporting:

    @pytest.mark.unit
    def test_it_says_how_many_bars_it_removed(self):
        """Sin la cifra, purgar es un cambio invisible: los números se mueven un
        poco y nadie sabe si fue la corrección o la semilla."""
        rep = leakage_report(2000, 4, 5)
        assert rep["gap_bars"] == 5 + 20
        assert rep["embargo_bars"] == 20
        assert "solapamiento de etiquetas" in rep["note"]

    @pytest.mark.unit
    def test_it_reports_folds_actually_usable_not_requested(self):
        rep = leakage_report(1000, 4, 400, embargo_pct=0.0)
        assert rep["n_splits_usable"] < rep["n_splits_requested"]

    @pytest.mark.unit
    def test_the_index_helper_matches_the_splitter(self):
        folds = purged_walk_forward(1000, 4, 5)
        direct = list(PurgedTimeSeriesSplit(4, 5, DEFAULT_EMBARGO_PCT).split(_X()))
        assert len(folds) == len(direct)
        for (tr_a, te_a), (tr_b, te_b) in zip(folds, direct):
            assert np.array_equal(tr_a, tr_b) and np.array_equal(te_a, te_b)
