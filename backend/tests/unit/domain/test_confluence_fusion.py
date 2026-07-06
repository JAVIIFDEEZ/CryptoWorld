"""
tests/unit/domain/test_confluence_fusion.py — Motor de confluencia (dominio).

Verifica el aprendizaje de pesos desde el acierto histórico (promoción de
fuentes con edge, degradación de las que fallan, arranque en frío honesto) y
la fusión (renormalización sobre disponibles, acuerdo ponderado, veredictos y
el caso INSUFICIENTE con < 2 fuentes).
"""

import pytest

from core.domain.services.confluence_fusion import (
    MIN_SAMPLE, PRIOR_WEIGHTS, fuse, learn_weights,
)


def _rows(source: str, n: int, hit_rate: float, score: float = 0.5) -> list[dict]:
    """n lecturas resueltas de una fuente con el hit_rate exacto pedido."""
    hits = int(round(n * hit_rate))
    out = []
    for i in range(n):
        correct = i < hits
        ret = 1.0 if (score > 0) == correct else -1.0
        out.append({"scores": {source: score}, "actual_return_pct": ret})
    return out


class TestLearnWeights:

    @pytest.mark.unit
    def test_cold_start_uses_priors(self):
        w = learn_weights([])
        assert all(v["mode"] == "a_priori" for v in w.values())
        assert w["technical"]["weight"] == pytest.approx(PRIOR_WEIGHTS["technical"], abs=1e-4)
        assert sum(v["weight"] for v in w.values()) == pytest.approx(1.0, abs=1e-3)

    @pytest.mark.unit
    def test_accurate_source_gains_weight_inaccurate_loses(self):
        rows = _rows("ml", 40, hit_rate=0.70) + _rows("news", 40, hit_rate=0.30)
        w = learn_weights(rows)
        assert w["ml"]["mode"] == "aprendido" and w["ml"]["hit_rate"] == pytest.approx(0.70)
        assert w["news"]["mode"] == "aprendido" and w["news"]["hit_rate"] == pytest.approx(0.30)
        # Con el mismo prior relativo, la fuente con edge pesa más que su prior
        # renormalizado y la que falla pesa menos.
        assert w["ml"]["weight"] > PRIOR_WEIGHTS["ml"] / (PRIOR_WEIGHTS["ml"] + sum(PRIOR_WEIGHTS.values()))
        assert w["news"]["weight"] < w["ml"]["weight"]

    @pytest.mark.unit
    def test_below_min_sample_stays_prior(self):
        rows = _rows("onchain", MIN_SAMPLE - 1, hit_rate=1.0)
        w = learn_weights(rows)
        assert w["onchain"]["mode"] == "a_priori" and w["onchain"]["n"] == MIN_SAMPLE - 1

    @pytest.mark.unit
    def test_flat_scores_do_not_count_as_directional(self):
        rows = [{"scores": {"ml": 0.05}, "actual_return_pct": 1.0}] * 50
        w = learn_weights(rows)
        assert w["ml"]["n"] == 0    # |score| < umbral direccional: no evaluable


class TestFuse:

    def _weights(self):
        return learn_weights([])

    @pytest.mark.unit
    def test_insufficient_with_less_than_two_sources(self):
        out = fuse({"technical": {"score": 0.8, "available": True},
                    "ml": {"score": None, "available": False}}, self._weights())
        assert out["verdict"] == "INSUFICIENTE"

    @pytest.mark.unit
    def test_bullish_confluence_when_sources_agree(self):
        sources = {
            "technical": {"score": 0.6, "available": True},
            "ml": {"score": 0.4, "available": True},
            "onchain": {"score": 0.5, "available": True},
            "news": {"score": 0.3, "available": True},
        }
        out = fuse(sources, self._weights())
        assert out["verdict"] == "CONFLUENCIA_ALCISTA"
        assert out["score"] > 0.3 and out["agreement_pct"] == 100.0

    @pytest.mark.unit
    def test_disagreement_yields_mixto_not_fake_consensus(self):
        sources = {
            "technical": {"score": 0.9, "available": True},
            "ml": {"score": -0.8, "available": True},
            "onchain": {"score": 0.5, "available": True},
            "news": {"score": -0.4, "available": True},
        }
        out = fuse(sources, self._weights())
        assert out["verdict"] in ("MIXTO", "NEUTRAL")

    @pytest.mark.unit
    def test_weights_renormalized_over_available(self):
        # Solo 2 fuentes vivas y de acuerdo: la confluencia funciona igual.
        sources = {
            "technical": {"score": 0.5, "available": True},
            "ml": {"score": None, "available": False},
            "onchain": {"score": 0.6, "available": True},
            "news": {"score": None, "available": False},
        }
        out = fuse(sources, self._weights())
        assert out["sources_available"] == 2
        assert out["verdict"] == "CONFLUENCIA_ALCISTA"
        # El score fusionado está entre los dos scores (media ponderada)
        assert 0.5 <= out["score"] <= 0.6
