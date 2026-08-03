"""
test_purged_cpcv.py — Validación cruzada combinatoria purgada (G2).

El walk-forward recorre UN camino histórico: su Sharpe es un punto con mucha
varianza, y basta que un tramo bueno caiga donde caiga para cambiar el
veredicto. El CPCV toma todas las combinaciones de k bloques como test y
devuelve la **distribución** de la que ese punto era una sola muestra.

Se fija aquí:
  · la combinatoria produce C(N,k) caminos y sus percentiles;
  · el percentil bajo distingue una estrategia consistente de otra que solo
    funciona en un tramo — que es justo lo que el walk-forward simple puede
    no ver;
  · el embargo descarta las velas de calentamiento en cada frontera de bloque;
  · cada bloque se evalúa aislado (ninguno ve datos de otro).
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services import backtest_robustness as rb
from core.domain.services import strategy_evaluation as ev
from core.domain.services.strategy_spec import seed_specs


def _blocks(means: list[float], n: int = 60, sd: float = 0.01, seed: int = 0) -> list:
    """Un bloque de retornos por cada media indicada."""
    rng = np.random.default_rng(seed)
    return [list(rng.normal(mu, sd, n)) for mu in means]


class TestCombinatorialPaths:

    @pytest.mark.unit
    def test_produces_all_combinations_of_k_blocks(self):
        out = rb.combinatorial_paths(_blocks([0.001] * 6), k=2)
        assert out["n_blocks"] == 6
        assert out["n_paths"] == 15          # C(6,2)
        assert out["blocks_per_path"] == 2

    @pytest.mark.unit
    def test_percentiles_are_ordered(self):
        out = rb.combinatorial_paths(_blocks([0.002, -0.001, 0.003, 0.0, 0.001, -0.002]), k=2)
        assert out["sharpe_min"] <= out["sharpe_p5"] <= out["sharpe_p25"]
        assert out["sharpe_p25"] <= out["sharpe_median"] <= out["sharpe_p75"]
        assert out["sharpe_p75"] <= out["sharpe_max"]

    @pytest.mark.unit
    def test_consistent_strategy_has_a_high_floor(self):
        """Si todos los bloques van bien, ningún troceo la deja en negativo."""
        out = rb.combinatorial_paths(_blocks([0.004] * 6, sd=0.008, seed=1), k=2)
        assert out["sharpe_p5"] > 0
        assert out["pct_paths_positive"] == 100.0

    @pytest.mark.unit
    def test_one_lucky_block_collapses_the_low_percentile(self):
        """El caso que el walk-forward simple puede no ver: la estrategia solo
        gana en un tramo. La media sigue siendo decente, pero el percentil bajo
        —la cifra honesta— se hunde."""
        lucky = _blocks([0.02, -0.001, -0.001, -0.001, -0.001, -0.001], sd=0.008, seed=2)
        out = rb.combinatorial_paths(lucky, k=2)

        assert out["sharpe_max"] > 0            # existe un camino que brilla
        assert out["sharpe_p5"] < 0             # y el escenario adverso pierde
        assert out["pct_paths_positive"] < 50.0

    @pytest.mark.unit
    def test_caps_the_combinatorial_explosion(self):
        out = rb.combinatorial_paths(_blocks([0.001] * 20), k=4, max_paths=50)
        assert out["n_paths"] == 50

    @pytest.mark.unit
    @pytest.mark.parametrize("blocks,k", [([], 2), ([[0.1, 0.2]], 2)])
    def test_insufficient_blocks_reports_instead_of_crashing(self, blocks, k):
        assert rb.combinatorial_paths(blocks, k=k)["n_paths"] == 0

    @pytest.mark.unit
    def test_is_deterministic(self):
        b = _blocks([0.001, 0.002, -0.001, 0.0, 0.003], seed=7)
        assert rb.combinatorial_paths(b, k=2) == rb.combinatorial_paths(b, k=2)


def _mean_reverting_df(n=900, seed=42):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    price = np.maximum(100 + 22 * np.sin(t / 22.0) + 6 * np.sin(t / 7.0) + rng.normal(0, 0.5, n), 5.0)
    return pd.DataFrame({
        "timestamp": (1_600_000_000 + t * 86400) * 1000,
        "open": price, "high": price + 0.3, "low": price - 0.3,
        "close": price, "volume": [1000.0] * n,
    })


class TestPurgedCpcvOnSpecs:

    @pytest.fixture
    def spec(self):
        return seed_specs()[0]

    @pytest.mark.unit
    def test_returns_a_distribution_not_a_point(self, spec):
        out = ev.purged_cpcv(_mean_reverting_df(), spec, n_blocks=6, k=2)
        assert out["n_paths"] == 15
        assert out["sharpe_p5"] <= out["sharpe_median"] <= out["sharpe_max"]
        assert len(out["blocks"]) == 6

    @pytest.mark.unit
    def test_embargo_drops_the_warmup_bars_of_each_block(self, spec):
        """Las primeras velas de un bloque tienen los indicadores a medio
        calentar: cualquier lectura ahí se calcula sobre una ventana incompleta."""
        df = _mean_reverting_df()
        strict = ev.purged_cpcv(df, spec, n_blocks=6, k=2, embargo_pct=0.20)
        loose = ev.purged_cpcv(df, spec, n_blocks=6, k=2, embargo_pct=0.0)

        assert strict["embargo_bars"] > loose["embargo_bars"]
        assert (sum(b["candles"] for b in strict["blocks"])
                < sum(b["candles"] for b in loose["blocks"]))

    @pytest.mark.unit
    def test_blocks_do_not_see_each_other(self, spec):
        """La purga efectiva: el resultado de un bloque no cambia según qué
        bloques lo acompañen, porque cada uno se backtestea aislado."""
        df = _mean_reverting_df()
        six = ev.purged_cpcv(df, spec, n_blocks=6, k=2)
        six_again = ev.purged_cpcv(df, spec, n_blocks=6, k=3)
        assert [b["sharpe"] for b in six["blocks"]] == [b["sharpe"] for b in six_again["blocks"]]

    @pytest.mark.unit
    def test_short_history_reports_instead_of_crashing(self, spec):
        out = ev.purged_cpcv(_mean_reverting_df(n=100), spec, n_blocks=8, k=2)
        assert out["n_paths"] == 0
        assert "insuficiente" in out["note"]

    @pytest.mark.unit
    def test_documents_why_the_classic_purge_does_not_apply(self, spec):
        """El motor no entrena nada en el walk-forward: el spec viene fijo del
        buscador. Purgar el train no cerraría ninguna fuga, y el resultado debe
        decirlo en vez de aparentar un rigor que no tiene."""
        out = ev.purged_cpcv(_mean_reverting_df(), spec, n_blocks=6, k=2)
        assert "no se entrena nada" in out["purge_note"]


class TestGatingCarriesTheDistribution:

    @pytest.mark.unit
    def test_gate_spec_reports_cpcv_without_gating_on_it(self):
        """Decisión de producto: se reporta, no bloquea. El gating sigue
        decidiéndose por los checks de siempre hasta calibrar un umbral con
        datos reales."""
        out = ev.gate_spec(
            _mean_reverting_df(), seed_specs()[0],
            ev.GatingThresholds(wf_splits=3, pbo_neighbors=4, mc_sims=60, cpcv_blocks=6),
        )

        assert out["metrics"]["cpcv"]["n_paths"] == 15
        assert out["metrics"]["cpcv_sharpe_p5"] is not None
        assert "cpcv_p5" not in out["checks"]
