"""
test_retest_cascade.py — Cascada de retests (G5).

StrategyQuant retiene una estrategia solo si sobrevive a una cascada de
perturbaciones. Cada prueba ataca una forma distinta de sobreajuste:

  · ruido en los precios → ¿dependía de las velas EXACTAS que ocurrieron?
  · desplazamiento del arranque → ¿dependía de dónde se cortó el histórico?
  · omisión de operaciones → ¿dependía de capturarlas TODAS?
  · sensibilidad paramétrica → ¿dependía del parámetro exacto?
  · estabilidad temporal → ¿el beneficio estaba repartido, o fue una racha?

El caso que da sentido a todo esto es la estrategia que brilla sobre los datos
reales y se desploma en cuanto las velas se mueven un poco: eso es curve
fitting, y ningún walk-forward lo detecta.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services import strategy_evaluation as ev
from core.domain.services.strategy_spec import seed_specs


def _df(n=600, seed=42):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    close = np.maximum(100 + 20 * np.sin(t / 20.0) + rng.normal(0, 0.6, n), 5.0)
    open_ = np.concatenate([[close[0]], close[:-1]])
    return pd.DataFrame({
        "timestamp": (1_600_000_000 + t * 86400) * 1000,
        "open": open_,
        "high": np.maximum(close, open_) + 0.4,
        "low": np.minimum(close, open_) - 0.4,
        "close": close, "volume": [1000.0] * n,
    })


@pytest.fixture(scope="module")
def spec():
    return seed_specs()[0]


class TestNoiseTest:

    @pytest.mark.unit
    def test_reports_the_distribution_under_noise(self, spec):
        out = ev.noise_test(_df(), spec, n_runs=6)
        assert out["n_runs"] == 6
        assert out["base_sharpe"] is not None
        assert 0.0 <= out["pct_runs_positive"] <= 100.0

    @pytest.mark.unit
    def test_more_noise_degrades_more(self, spec):
        """Cuanto más se mueven las velas, más se aleja el resultado del
        original: si no fuera así, el ruido no estaría llegando al backtest."""
        df = _df()
        gentle = ev.noise_test(df, spec, n_runs=8, atr_fraction=0.05, seed=1)
        harsh = ev.noise_test(df, spec, n_runs=8, atr_fraction=1.5, seed=1)

        gentle_gap = abs(gentle["noisy_sharpe_median"] - gentle["base_sharpe"])
        harsh_gap = abs(harsh["noisy_sharpe_median"] - harsh["base_sharpe"])
        assert harsh_gap > gentle_gap

    @pytest.mark.unit
    def test_is_deterministic_for_a_given_seed(self, spec):
        df = _df()
        assert (ev.noise_test(df, spec, n_runs=4, seed=9)
                == ev.noise_test(df, spec, n_runs=4, seed=9))

    @pytest.mark.unit
    def test_short_series_reports_instead_of_crashing(self, spec):
        assert ev.noise_test(_df(n=20), spec, n_runs=3)["n_runs"] == 0


class TestStartingBarTest:

    @pytest.mark.unit
    def test_evaluates_each_offset(self, spec):
        out = ev.starting_bar_test(_df(), spec, offsets=(0, 7, 19))
        assert out["n_offsets"] == 3
        assert [r["offset"] for r in out["results"]] == [0, 7, 19]

    @pytest.mark.unit
    def test_skips_offsets_that_leave_too_little_history(self, spec):
        out = ev.starting_bar_test(_df(n=100), spec, offsets=(0, 90))
        assert out["n_offsets"] == 1        # 100−90 = 10 velas no dan para nada

    @pytest.mark.unit
    def test_reports_dispersion_across_offsets(self, spec):
        out = ev.starting_bar_test(_df(), spec)
        assert out["sharpe_std"] >= 0
        assert out["sharpe_min"] <= out["sharpe_mean"]


class TestSkipTradesTest:

    @staticmethod
    def _trades(pnls):
        return [{"pnl_pct": p} for p in pnls]

    @pytest.mark.unit
    def test_broad_edge_survives_missing_trades(self):
        """Beneficio repartido entre muchas operaciones: perderse algunas no
        cambia el signo del resultado."""
        out = ev.skip_trades_test(self._trades([1.2] * 40), skip_pct=0.2, n_runs=100)
        assert out["pct_runs_profitable"] == 100.0
        assert out["trades_kept"] == 32

    @pytest.mark.unit
    def test_edge_concentrated_in_one_trade_is_fragile(self):
        """Un beneficio que vive de UN acierto entre muchas pérdidas se
        desmorona en cuanto se falla esa ejecución. El backtest completo daba
        ganancias; la distribución dice lo frágil que era.

        Un solo ganador dominante es la forma pura del caso: perderse cualquier
        otra operación apenas mueve el total, pero perderse esa lo invierte."""
        pnls = [100.0] + [-2.0] * 40
        out = ev.skip_trades_test(self._trades(pnls), skip_pct=0.2, n_runs=400, seed=3)

        assert out["full_pnl_pct"] > 0            # el backtest completo gana
        assert out["pct_runs_profitable"] < 90.0  # pero no siempre
        assert out["pnl_p5_pct"] < 0              # y el escenario adverso pierde

    @pytest.mark.unit
    def test_too_few_trades_reports_instead_of_guessing(self):
        assert ev.skip_trades_test([{"pnl_pct": 1.0}] * 3)["n_runs"] == 0


class TestCascade:

    @pytest.mark.unit
    def test_aggregates_every_check_with_a_verdict(self, spec):
        out = ev.retest_cascade(_df(), spec, noise_runs=5)
        assert set(out["checks"]) == {
            "noise", "starting_bar", "skip_trades", "parameter_sensitivity",
            "temporal_stability",
        }
        assert isinstance(out["survived"], bool)
        assert out["survived"] == (out["failed"] == [])

    @pytest.mark.unit
    def test_reports_where_the_edge_lives(self, spec):
        """El reparto por régimen no condena a nadie: un edge que solo vive en
        mercados turbulentos sigue siendo un edge. Lo que no vale es ignorarlo
        al asignarle capital."""
        out = ev.retest_cascade(_df(), spec, noise_runs=3)
        assert "by_regime" in out
        assert "temporal_stability" in out

    @pytest.mark.unit
    def test_a_test_that_could_not_run_is_not_counted_as_a_failure(self, spec):
        """Ausencia de evidencia no es evidencia de fragilidad: si la serie no
        da para una prueba, esa prueba no puede condenar a la estrategia.

        Con 59 velas ningún desplazamiento del arranque deja las 60 que exige
        un backtest, así que esa prueba no llega a ejecutarse."""
        out = ev.retest_cascade(_df(n=59), spec, noise_runs=3)
        assert out["starting_bar"]["n_offsets"] == 0
        assert out["checks"]["starting_bar"] is True

    @pytest.mark.unit
    def test_computes_its_own_trades_when_not_provided(self, spec):
        out = ev.retest_cascade(_df(), spec, noise_runs=3)
        assert "skip_trades" in out

    @pytest.mark.unit
    def test_note_names_the_failing_checks(self, spec):
        out = ev.retest_cascade(_df(), spec, noise_runs=5)
        if out["failed"]:
            for name in out["failed"]:
                assert name in out["note"]
        else:
            assert "Sobrevive" in out["note"]
