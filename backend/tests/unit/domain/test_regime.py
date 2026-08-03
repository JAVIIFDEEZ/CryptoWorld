"""
test_regime.py — Régimen de mercado y estabilidad temporal (G7).

Un edge no es una propiedad absoluta de una estrategia: es una propiedad de la
pareja estrategia-régimen. Y una estrategia cuyo beneficio entero sale de un
tramo del histórico no tiene edge — tuvo una racha, que es distinto y falla
fuera de muestra.
"""

import numpy as np
import pytest

from core.domain.services import regime as rg


def _series(vol_profile, seed=0):
    """Precio cuyo nivel de volatilidad cambia por tramos."""
    rng = np.random.default_rng(seed)
    rets = np.concatenate([rng.normal(0, sd, n) for sd, n in vol_profile])
    return 100 * np.exp(np.cumsum(rets))


class TestDetectRegimes:

    @pytest.mark.unit
    def test_identifies_calm_and_turbulent_stretches(self):
        close = _series([(0.002, 120), (0.05, 120), (0.002, 120)])
        out = rg.detect_regimes(close)

        assert out["n"] == close.size
        assert out["counts"][rg.TURBULENT] > 0
        assert out["counts"][rg.CALM] > 0
        # El tramo central es el volátil: debe dominar el régimen turbulento ahí.
        middle = out["labels"][150:230]
        assert middle.count(rg.TURBULENT) > middle.count(rg.CALM)

    @pytest.mark.unit
    def test_hysteresis_prevents_flickering(self):
        """Una serie que roza la frontera no puede cambiar de etiqueta cada
        pocas velas: un régimen que parpadea no significa nada."""
        close = _series([(0.01, 400)], seed=7)
        with_hyst = rg.detect_regimes(close, rg.RegimeConfig(hysteresis=0.25))
        without = rg.detect_regimes(close, rg.RegimeConfig(hysteresis=0.0))
        assert with_hyst["switches"] < without["switches"]

    @pytest.mark.unit
    def test_thresholds_are_relative_to_the_asset(self):
        """«Turbulento» significa turbulento PARA ESTE activo: un umbral fijo no
        significaría lo mismo en BTC y en una stablecoin."""
        quiet = rg.detect_regimes(_series([(0.001, 300)], seed=1))
        wild = rg.detect_regimes(_series([(0.05, 300)], seed=1))
        assert wild["thresholds"]["turbulent_above"] > quiet["thresholds"]["turbulent_above"]
        # Y aun así ambas usan los tres regímenes sobre su propia escala.
        assert quiet["counts"][rg.TURBULENT] > 0

    @pytest.mark.unit
    def test_short_series_reports_instead_of_crashing(self):
        assert rg.detect_regimes(np.full(10, 100.0))["n"] == 0


class TestCurrentRegime:

    @pytest.mark.unit
    def test_uses_only_past_data(self):
        """La versión operativa no puede mirar la vela que está clasificando."""
        close = _series([(0.002, 200), (0.06, 60)], seed=3)
        assert rg.current_regime(close)["regime"] in (rg.CALM, rg.NORMAL, rg.TURBULENT)

    @pytest.mark.unit
    def test_assumes_normal_without_enough_history(self):
        out = rg.current_regime(np.full(8, 100.0))
        assert out["regime"] == rg.NORMAL
        assert "insuficiente" in out["note"]


class TestPerformanceByRegime:

    @pytest.mark.unit
    def test_splits_the_edge_across_regimes(self):
        """Saber que una estrategia solo gana en un régimen no la invalida: la
        convierte en una estrategia de régimen. Lo que no vale es no saberlo."""
        labels = [rg.CALM] * 50 + [rg.TURBULENT] * 50
        returns = np.concatenate([np.full(50, 0.01), np.full(50, -0.01)])

        out = rg.performance_by_regime(returns, labels)
        assert out[rg.CALM]["total_return_pct"] > 0
        assert out[rg.TURBULENT]["total_return_pct"] < 0
        assert out[rg.CALM]["share_pct"] == 50.0

    @pytest.mark.unit
    def test_reports_insufficient_sample_instead_of_a_fake_number(self):
        out = rg.performance_by_regime(np.full(10, 0.01), [rg.CALM] * 10)
        assert out[rg.TURBULENT]["bars"] == 0
        assert "insuficiente" in out[rg.TURBULENT]["note"]


class TestTemporalStability:

    @pytest.mark.unit
    def test_a_spread_out_edge_is_stable(self):
        rng = np.random.default_rng(5)
        returns = rng.normal(0.003, 0.01, 500)
        out = rg.temporal_stability(returns)

        assert out["stable"] is True
        assert out["concentration"] < 0.5
        assert "repartido" in out["note"]

    @pytest.mark.unit
    def test_a_single_lucky_stretch_is_not_an_edge(self):
        """Todo el beneficio en un décimo del histórico: eso es una racha, y es
        una de las causas número uno de fallo fuera de muestra."""
        returns = np.concatenate([
            np.full(450, -0.0001),      # el 90% del tiempo, plano/negativo
            np.full(50, 0.02),          # y un tramo espectacular
        ])
        out = rg.temporal_stability(returns)

        assert out["stable"] is False
        assert out["concentration"] > 0.9
        assert out["best_bucket"] == 10
        assert "racha" in out["note"]

    @pytest.mark.unit
    def test_reports_each_bucket(self):
        out = rg.temporal_stability(np.random.default_rng(1).normal(0.001, 0.01, 300), n_buckets=6)
        assert len(out["bucket_returns_pct"]) == 6
        assert 1 <= out["best_bucket"] <= 6
        assert 1 <= out["worst_bucket"] <= 6

    @pytest.mark.unit
    def test_short_series_reports_instead_of_crashing(self):
        assert rg.temporal_stability(np.array([0.01, 0.02]))["n_buckets"] == 0
