"""
tests/integration/test_prediction_tracking.py — Registro y verificación de
predicciones ML (bucle de mejora continua).
"""

from datetime import timedelta

import numpy as np
import pandas as pd
import pytest
from django.utils import timezone

from core.application.use_cases.ohlcv_fetcher import OhlcvFetchResult
from core.application.use_cases.track_predictions import (
    PredictionMonitoringUseCase, PredictionTrackRecordUseCase,
    ResolvePredictionsUseCase, log_prediction,
)


@pytest.fixture
def btc(db):
    from core.infrastructure.persistence.models import CryptoAsset
    return CryptoAsset.objects.create(symbol="BTC", name="Bitcoin")


class TestLogging:

    @pytest.mark.integration
    def test_log_creates_pending_record_with_future_resolve(self, btc, test_user):
        from core.infrastructure.persistence.models import PredictionRecord
        pred = {"prediction": "ALCISTA", "prob_up": 0.62, "confidence": 0.62,
                "edge": 0.05, "oos_accuracy": 0.58, "verdict": "EDGE", "model": "rf"}
        log_prediction(pred, "BTC", "1d", horizon=5, last_close=100.0, owner=test_user)
        rec = PredictionRecord.objects.get()
        assert rec.status == "pending" and rec.predicted == "ALCISTA"
        assert rec.price_at_prediction == 100.0 and rec.owner_id == test_user.id
        assert rec.resolve_at > timezone.now()   # 5 días en el futuro (1d × 5)

    @pytest.mark.integration
    def test_insufficient_prediction_not_logged(self, btc):
        from core.infrastructure.persistence.models import PredictionRecord
        log_prediction({"prediction": "INSUFFICIENT_DATA"}, "BTC", "1d", 5, last_close=100.0)
        assert PredictionRecord.objects.count() == 0


class TestResolution:

    def _record(self, btc, predicted, resolve_ago_h=1):
        from core.infrastructure.persistence.models import PredictionRecord
        return PredictionRecord.objects.create(
            asset=btc, asset_symbol="BTC", interval="1d", horizon=5,
            predicted=predicted, prob_up=0.6, confidence=0.6, price_at_prediction=100.0,
            verdict="EDGE", resolve_at=timezone.now() - timedelta(hours=resolve_ago_h),
        )

    @pytest.mark.integration
    def test_resolves_correct_prediction(self, btc, monkeypatch):
        rec = self._record(btc, "ALCISTA")
        # OHLCV con una vela en la fecha de resolución a precio 110 (subió) → acierto
        resolve_ms = int(rec.resolve_at.timestamp() * 1000)
        df = pd.DataFrame({"timestamp": [resolve_ms, resolve_ms + 86400000],
                           "open": [110, 111], "high": [111, 112], "low": [109, 110],
                           "close": [110.0, 111.0], "volume": [1.0, 1.0]})
        monkeypatch.setattr("core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
                            lambda symbol, interval="1d", limit=500, **kw: OhlcvFetchResult(df=df, source="binance"))
        out = ResolvePredictionsUseCase().execute()
        assert out == {"resolved": 1, "correct": 1}
        rec.refresh_from_db()
        assert rec.status == "correct" and rec.actual_direction == "ALCISTA"
        assert rec.price_at_resolution == 110.0 and rec.actual_return_pct == pytest.approx(10.0)

    @pytest.mark.integration
    def test_resolves_incorrect_prediction(self, btc, monkeypatch):
        rec = self._record(btc, "ALCISTA")
        resolve_ms = int(rec.resolve_at.timestamp() * 1000)
        df = pd.DataFrame({"timestamp": [resolve_ms], "open": [90], "high": [91], "low": [89],
                           "close": [90.0], "volume": [1.0]})
        monkeypatch.setattr("core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
                            lambda symbol, interval="1d", limit=500, **kw: OhlcvFetchResult(df=df, source="binance"))
        ResolvePredictionsUseCase().execute()
        rec.refresh_from_db()
        assert rec.status == "incorrect" and rec.actual_direction == "BAJISTA"

    @pytest.mark.integration
    def test_not_resolved_if_data_not_caught_up(self, btc, monkeypatch):
        rec = self._record(btc, "ALCISTA")
        # OHLCV solo con velas ANTERIORES a la fecha de resolución → sigue pendiente
        old_ms = int((rec.resolve_at - timedelta(days=10)).timestamp() * 1000)
        df = pd.DataFrame({"timestamp": [old_ms], "open": [100], "high": [101], "low": [99],
                           "close": [100.0], "volume": [1.0]})
        monkeypatch.setattr("core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
                            lambda symbol, interval="1d", limit=500, **kw: OhlcvFetchResult(df=df, source="binance"))
        out = ResolvePredictionsUseCase().execute()
        assert out["resolved"] == 0
        rec.refresh_from_db()
        assert rec.status == "pending"


class TestTrackRecord:

    @pytest.mark.integration
    def test_accuracy_and_by_verdict(self, btc, test_user):
        from core.infrastructure.persistence.models import PredictionRecord
        # 2 EDGE (1 acierto, 1 fallo) + 1 NO_EDGE acierto
        common = dict(asset=btc, asset_symbol="BTC", interval="1d", horizon=5,
                      prob_up=0.6, confidence=0.6, price_at_prediction=100.0,
                      owner=test_user, resolve_at=timezone.now())
        PredictionRecord.objects.create(predicted="ALCISTA", verdict="EDGE", status="correct", **common)
        PredictionRecord.objects.create(predicted="ALCISTA", verdict="EDGE", status="incorrect", **common)
        PredictionRecord.objects.create(predicted="BAJISTA", verdict="NO_EDGE", status="correct", **common)

        tr = PredictionTrackRecordUseCase().execute(owner=test_user)
        assert tr["resolved"] == 3 and tr["correct"] == 2
        assert tr["accuracy"] == pytest.approx(2 / 3, abs=1e-3)
        assert tr["by_verdict"]["EDGE"] == {"n": 2, "accuracy": 0.5}
        assert tr["by_verdict"]["NO_EDGE"] == {"n": 1, "accuracy": 1.0}

    @pytest.mark.integration
    def test_endpoint_requires_auth(self, api_client):
        assert api_client.get("/api/analysis/predictions/").status_code == 401

    @pytest.mark.integration
    def test_endpoint_returns_track_record(self, authenticated_client, btc):
        resp = authenticated_client.get("/api/analysis/predictions/")
        assert resp.status_code == 200
        assert set(resp.data) >= {"total", "resolved", "pending", "correct", "accuracy", "by_verdict", "recent"}


class TestMonitoring:

    def _resolved(self, btc, user, n, n_correct, oos, resolved_at=None):
        """Crea `n` predicciones resueltas (`n_correct` aciertos) con OOS prometida."""
        from core.infrastructure.persistence.models import PredictionRecord
        base = resolved_at or timezone.now()
        for i in range(n):
            PredictionRecord.objects.create(
                asset=btc, asset_symbol="BTC", interval="1d", horizon=5,
                predicted="ALCISTA", prob_up=0.6, confidence=0.6, price_at_prediction=100.0,
                oos_accuracy=oos, verdict="EDGE", owner=user,
                status="correct" if i < n_correct else "incorrect",
                resolve_at=base, resolved_at=base + timedelta(minutes=i),
            )

    @pytest.mark.integration
    def test_insufficient_sample(self, btc, test_user):
        self._resolved(btc, test_user, n=4, n_correct=3, oos=0.6)
        m = PredictionMonitoringUseCase().execute(owner=test_user)
        assert m["status"] == "insufficient"
        assert m["n_resolved"] == 4

    @pytest.mark.integration
    def test_ok_when_realized_matches_expected(self, btc, test_user):
        # 12 resueltas, 7 aciertos (~58%), prometido 56% → en línea (ok)
        self._resolved(btc, test_user, n=12, n_correct=7, oos=0.56)
        m = PredictionMonitoringUseCase().execute(owner=test_user)
        assert m["status"] == "ok"
        assert m["realized_accuracy"] == pytest.approx(7 / 12, abs=1e-3)
        assert m["expected_accuracy"] == pytest.approx(0.56, abs=1e-3)
        assert m["gap"] == pytest.approx(7 / 12 - 0.56, abs=1e-3)

    @pytest.mark.integration
    def test_drift_when_realized_far_below_expected(self, btc, test_user):
        # 12 resueltas, 3 aciertos (25%), prometido 60% → brecha -35% → drift
        self._resolved(btc, test_user, n=12, n_correct=3, oos=0.60)
        m = PredictionMonitoringUseCase().execute(owner=test_user)
        assert m["status"] == "drift"
        assert m["gap"] < m["thresholds"]["drift"]
        assert m["by_asset"]["BTC"]["n"] == 12

    @pytest.mark.integration
    def test_series_has_buckets(self, btc, test_user):
        self._resolved(btc, test_user, n=16, n_correct=8, oos=0.55)
        m = PredictionMonitoringUseCase().execute(owner=test_user, buckets=4)
        assert 1 <= len(m["series"]) <= 4
        assert sum(b["n"] for b in m["series"]) == 16

    @pytest.mark.integration
    def test_endpoint_requires_auth(self, api_client):
        assert api_client.get("/api/analysis/predictions/monitoring/").status_code == 401

    @pytest.mark.integration
    def test_endpoint_returns_monitoring(self, authenticated_client, btc):
        resp = authenticated_client.get("/api/analysis/predictions/monitoring/")
        assert resp.status_code == 200
        assert set(resp.data) >= {"status", "expected_accuracy", "realized_accuracy", "gap",
                                  "n_resolved", "series", "by_asset", "thresholds"}
