"""
test_hrp.py — Hierarchical Risk Parity (G6).

Markowitz invierte la matriz de covarianzas; con activos correlacionados esa
matriz está mal condicionada y al invertirla los errores de estimación se
amplifican. HRP no invierte nada: agrupa por correlación, reordena y reparte por
bisección recursiva.

Lo que estos tests fijan es el comportamiento que justifica el método: que el
peso huya de la concentración y de la volatilidad, y que el resultado no dependa
del orden en que lleguen las columnas.
"""

import numpy as np
import pytest

from core.domain.services import hrp


def _series(n=400, sd=0.01, seed=0, base=None):
    rng = np.random.default_rng(seed)
    noise = rng.normal(0, sd, n)
    return noise if base is None else base * 0.98 + noise * 0.02


class TestCorrelationDistance:

    @pytest.mark.unit
    def test_identical_series_are_at_distance_zero(self):
        d = hrp.correlation_distance(np.array([[1.0, 1.0], [1.0, 1.0]]))
        assert d[0, 1] == pytest.approx(0.0)

    @pytest.mark.unit
    def test_opposite_series_are_at_distance_one(self):
        d = hrp.correlation_distance(np.array([[1.0, -1.0], [-1.0, 1.0]]))
        assert d[0, 1] == pytest.approx(1.0)

    @pytest.mark.unit
    def test_uncorrelated_sit_in_between(self):
        d = hrp.correlation_distance(np.array([[1.0, 0.0], [0.0, 1.0]]))
        assert d[0, 1] == pytest.approx(np.sqrt(0.5))


class TestWeights:

    @pytest.mark.unit
    def test_weights_sum_to_one(self):
        M = np.column_stack([_series(seed=s) for s in range(5)])
        out = hrp.hierarchical_risk_parity(M)
        assert sum(out["weights"].values()) == pytest.approx(1.0, abs=1e-6)

    @pytest.mark.unit
    def test_the_volatile_strategy_gets_less_weight(self):
        """Paridad de RIESGO: a igualdad de todo lo demás, la que más oscila
        aporta menos capital."""
        calm = _series(sd=0.005, seed=1)
        wild = _series(sd=0.05, seed=2)
        out = hrp.hierarchical_risk_parity(np.column_stack([calm, wild]), ["calma", "volátil"])
        assert out["weights"]["calma"] > out["weights"]["volátil"]

    @pytest.mark.unit
    def test_a_cluster_of_clones_does_not_capture_the_book(self):
        """Tres estrategias casi idénticas y una independiente: el clúster no
        puede llevarse tres veces el peso por ser tres copias del mismo edge."""
        base = _series(seed=10)
        clones = [base * 0.98 + _series(sd=0.001, seed=100 + i) for i in range(3)]
        independent = _series(seed=99)

        out = hrp.hierarchical_risk_parity(
            np.column_stack(clones + [independent]),
            ["clon1", "clon2", "clon3", "independiente"],
        )
        cluster_weight = sum(out["weights"][f"clon{i}"] for i in (1, 2, 3))
        assert out["weights"]["independiente"] > cluster_weight / 3
        assert cluster_weight < 0.9

    @pytest.mark.unit
    def test_diversifies_at_least_as_well_as_equal_weight(self):
        """Con estrategias de volatilidad muy dispar, HRP debe rebajar la
        volatilidad de cartera frente a repartir a partes iguales."""
        M = np.column_stack([
            _series(sd=0.004, seed=1), _series(sd=0.006, seed=2),
            _series(sd=0.05, seed=3), _series(sd=0.08, seed=4),
        ])
        out = hrp.hierarchical_risk_parity(M)
        assert out["portfolio_volatility"] < out["equal_weight_volatility"]

    @pytest.mark.unit
    def test_is_invariant_to_column_order(self):
        """Los pesos son una propiedad de las series, no del orden en que
        lleguen: si dependieran del orden, el método no sería reproducible."""
        cols = [_series(sd=0.01 * (i + 1), seed=i) for i in range(4)]
        names = ["a", "b", "c", "d"]

        straight = hrp.hierarchical_risk_parity(np.column_stack(cols), names)["weights"]
        perm = [2, 0, 3, 1]
        shuffled = hrp.hierarchical_risk_parity(
            np.column_stack([cols[i] for i in perm]), [names[i] for i in perm],
        )["weights"]

        for name in names:
            assert straight[name] == pytest.approx(shuffled[name], abs=1e-6)


class TestReporting:

    @pytest.mark.unit
    def test_effective_number_of_strategies(self):
        """1/HHI: cuántas estrategias aporta REALMENTE la cartera. Cuatro pesos
        iguales dan 4; una que se lo lleva casi todo se acerca a 1."""
        M = np.column_stack([_series(sd=0.01, seed=s) for s in range(4)])
        out = hrp.hierarchical_risk_parity(M)
        assert 1.0 <= out["effective_n_strategies"] <= 4.0

    @pytest.mark.unit
    def test_reports_the_ordering_of_the_tree(self):
        M = np.column_stack([_series(seed=s) for s in range(4)])
        out = hrp.hierarchical_risk_parity(M, ["w", "x", "y", "z"])
        assert sorted(out["order"]) == [0, 1, 2, 3]
        assert len(out["ordered_labels"]) == 4


class TestDegenerateInputs:

    @pytest.mark.unit
    def test_single_strategy_takes_everything(self):
        out = hrp.hierarchical_risk_parity(np.column_stack([_series()]), ["única"])
        assert out["weights"] == {"única": 1.0}

    @pytest.mark.unit
    def test_too_little_history_falls_back_to_equal_weight(self):
        out = hrp.hierarchical_risk_parity(np.array([[0.01, 0.02]]), ["a", "b"])
        assert out["weights"] == {"a": 0.5, "b": 0.5}
        assert "insuficiente" in out["note"]

    @pytest.mark.unit
    def test_constant_series_do_not_break_the_correlation(self):
        """Una estrategia que no opera da retornos constantes: sin varianza no
        hay correlación definida, y eso no puede tumbar el cálculo."""
        M = np.column_stack([np.zeros(50), _series(n=50, seed=3)])
        out = hrp.hierarchical_risk_parity(M, ["parada", "activa"])
        assert sum(out["weights"].values()) == pytest.approx(1.0, abs=1e-6)

    @pytest.mark.unit
    def test_empty_matrix_reports_instead_of_crashing(self):
        assert hrp.hierarchical_risk_parity(np.empty((0, 0)))["n_assets"] == 0
