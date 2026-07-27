"""
tests/unit/domain/test_ml_prediction.py — Predicción ML de dirección (honesta).

Verifica que la evaluación es out-of-sample (walk-forward), que reporta el edge
sobre la línea base y que, sobre ruido, NO inventa una ventaja inexistente.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services.technical_analysis_service import predict_price_direction


def _df(close):
    close = np.asarray(close, dtype=float)
    n = len(close)
    return pd.DataFrame({
        "timestamp": [1700000000000 + i * 86400000 for i in range(n)],
        "open": close, "high": close + 1, "low": close - 1, "close": close,
        "volume": [1000.0] * n,
    })


def _trend_cycle(n=400, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    return np.maximum(100 + 0.1 * t + 8 * np.sin(t / 20.0) + rng.normal(0, 1.5, n), 5.0)


def _noise(n=400, seed=2):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))


class TestPredictionStructure:

    @pytest.mark.unit
    def test_returns_oos_metrics_and_verdict(self):
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        for key in ("prediction", "confidence", "oos_accuracy", "baseline_accuracy",
                    "edge", "precision_up", "recall_up", "f1_up", "n_oos", "n_splits", "verdict"):
            assert key in r
        assert r["prediction"] in ("ALCISTA", "BAJISTA", "NEUTRAL")
        assert 0.0 <= r["confidence"] <= 1.0
        # El edge es exactamente la precisión OOS menos la línea base
        assert r["edge"] == pytest.approx(r["oos_accuracy"] - r["baseline_accuracy"], abs=1e-6)
        # La validación usó varios tramos OOS reales
        assert r["n_splits"] >= 3 and r["n_oos"] > 50

    @pytest.mark.unit
    def test_insufficient_data(self):
        r = predict_price_direction(_df(_trend_cycle(n=50)), horizon=5)
        assert r["prediction"] == "INSUFFICIENT_DATA"

    @pytest.mark.unit
    def test_deterministic(self):
        df = _df(_trend_cycle())
        a = predict_price_direction(df, horizon=5)
        b = predict_price_direction(df, horizon=5)
        assert a["oos_accuracy"] == b["oos_accuracy"] and a["prediction"] == b["prediction"]


class TestHonesty:

    @pytest.mark.unit
    def test_no_edge_on_pure_noise(self):
        """Sobre un random walk el modelo no debe reclamar ventaja: el edge OOS
        es ~0 y el veredicto no es EDGE (la clave de un ML honesto)."""
        r = predict_price_direction(_df(_noise()), horizon=5)
        assert r["edge"] < 0.04
        assert r["verdict"] in ("NO_EDGE", "WEAK")

    @pytest.mark.unit
    def test_baseline_is_majority_class_rate(self):
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        # La línea base = acierto de predecir siempre la clase mayoritaria ≥ 0.5
        assert r["baseline_accuracy"] >= 0.5
        assert r["baseline_accuracy"] == pytest.approx(max(r["up_rate"], 1 - r["up_rate"]), abs=1e-6)


class TestNeutralZone:

    @pytest.mark.unit
    def test_neutral_when_calibrated_prob_near_half(self):
        """prob_up dentro de [45%,55%] → NEUTRAL: no se proclama dirección a
        cara o cruz (y log_prediction no la registra en el historial)."""
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        band = r.get("neutral_band", 0.05)
        if abs(r["prob_up"] - 0.5) <= band:
            assert r["prediction"] == "NEUTRAL"
        else:
            assert r["prediction"] == ("ALCISTA" if r["prob_up"] > 0.5 else "BAJISTA")

    @pytest.mark.unit
    def test_neutral_band_exposed(self):
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        assert 0.0 < r["neutral_band"] <= 0.1


class TestCalibration:

    @pytest.mark.unit
    def test_probabilities_are_calibrated(self):
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        assert r["calibrated"] is True
        assert r["brier_score"] is not None and 0.0 <= r["brier_score"] <= 1.0
        # La confianza calibrada es una probabilidad válida
        assert 0.5 <= r["confidence"] <= 1.0
        assert r["prob_up"] is not None


class TestEnsemble:

    @pytest.mark.unit
    def test_model_is_voting_ensemble(self):
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        assert "Ensemble" in r["model"] and "RF+GB+LR" in r["model"]
        # Sigue exponiendo importancias (desde el RF interno)
        assert len(r["features_importance"]) >= 3


class TestLocalExplainability:
    """Atribución por oclusión: por qué el modelo decide ESTA vela."""

    @pytest.mark.unit
    def test_drivers_present_and_well_formed(self):
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        assert "drivers" in r and isinstance(r["drivers"], list)
        assert 1 <= len(r["drivers"]) <= 6
        for d in r["drivers"]:
            assert set(d.keys()) == {"feature", "contribution"}
            assert d["feature"] in [f["feature"] for f in r["features_importance"]] or isinstance(d["feature"], str)
            assert isinstance(d["contribution"], float)

    @pytest.mark.unit
    def test_drivers_sorted_by_absolute_contribution(self):
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        mags = [abs(d["contribution"]) for d in r["drivers"]]
        assert mags == sorted(mags, reverse=True)

    @pytest.mark.unit
    def test_drivers_deterministic(self):
        df = _df(_trend_cycle())
        a = predict_price_direction(df, horizon=5)
        b = predict_price_direction(df, horizon=5)
        assert a["drivers"] == b["drivers"]
