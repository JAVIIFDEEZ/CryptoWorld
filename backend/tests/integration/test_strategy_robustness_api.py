"""
tests/integration/test_strategy_robustness_api.py — Análisis profundo de un spec
y monitorización de señales (Módulo 2, mejoras profesionales).
"""

import numpy as np
import pandas as pd
import pytest

import core.application.use_cases.run_spec_robustness as rsr
from core.application.use_cases.ohlcv_fetcher import OhlcvFetchResult
from core.domain.services.strategy_spec import seed_specs


def _df(n=400, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    price = 100 + 22 * np.sin(t / 22.0) + 6 * np.sin(t / 7.0) + rng.normal(0, 0.5, n)
    price = np.maximum(price, 5.0)
    return pd.DataFrame({
        "timestamp": (1_600_000_000 + t * 86400) * 1000,
        "open": price, "high": price + 0.3, "low": price - 0.3,
        "close": price, "volume": [1000.0] * n,
    })


# Spec con entrada casi siempre activa (RSI < 85) y salida casi nunca (RSI > 85):
# señal determinista BUY, útil para la monitorización.
_ALWAYS_BUY = {
    "entry": {"combine": "AND", "conditions": [
        {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "lt", "threshold": 85.0}]},
    "exit": {"combine": "AND", "conditions": [
        {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "gt", "threshold": 85.0}]},
}


@pytest.fixture
def celery_eager(monkeypatch):
    from core.tasks import analyze_spec_robustness as task
    monkeypatch.setattr(task, "delay", lambda *a, **k: task.apply(args=a, kwargs=k))
    yield


@pytest.fixture
def fast_suite(monkeypatch):
    """OHLCV sintético para cualquier símbolo + presupuesto reducido."""
    monkeypatch.setattr(
        "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
        lambda symbol, interval="1d", limit=365, **kw: OhlcvFetchResult(df=_df(seed=hash(symbol) % 50), source="binance"),
    )
    monkeypatch.setattr(rsr, "config_for_preset",
                        lambda preset: rsr.SpecRobustnessConfig(n_neighbors=5, n_perms=10, n_sims=80, wf_splits=3))


class TestSpecRobustnessApi:

    @pytest.mark.integration
    def test_requires_authentication(self, api_client):
        assert api_client.post("/api/strategies/robustness/", {}, format="json").status_code == 401

    @pytest.mark.integration
    def test_requires_spec_or_id(self, authenticated_client):
        resp = authenticated_client.post("/api/strategies/robustness/", {"asset_symbol": "BTC"}, format="json")
        assert resp.status_code == 400

    @pytest.mark.integration
    def test_launch_then_poll_returns_report(self, authenticated_client, celery_eager, fast_suite):
        launch = authenticated_client.post(
            "/api/strategies/robustness/",
            {"asset_symbol": "BTC", "spec": seed_specs()[0], "preset": "fast"},
            format="json",
        )
        assert launch.status_code == 202
        job_id = launch.data["job_id"]

        status = authenticated_client.get(f"/api/strategies/robustness/{job_id}/")
        assert status.status_code == 200 and status.data["status"] == "SUCCESS"
        rep = status.data["result"]
        assert rep["verdict"] in ("ROBUSTA", "FRÁGIL", "SOBREAJUSTADA")
        assert "cross_asset" in rep and "consistency_score" in rep["cross_asset"]
        assert "diagnostics" in rep and "pbo" in rep["diagnostics"]

    @pytest.mark.integration
    def test_rejects_invalid_spec(self, authenticated_client, celery_eager, fast_suite):
        resp = authenticated_client.post(
            "/api/strategies/robustness/",
            {"asset_symbol": "BTC", "spec": {"entry": {}, "exit": {}}},
            format="json",
        )
        assert resp.status_code == 400


class TestMonitoring:

    def _make_strategy(self):
        from core.infrastructure.persistence.models import CryptoAsset, StrategyDefinition
        btc = CryptoAsset.objects.create(symbol="BTC", name="Bitcoin")
        return StrategyDefinition.objects.create(
            asset=btc, name="Monitor test", spec=_ALWAYS_BUY, spec_hash="m1",
            rank=1, passed_gating=True, status="validated",
        )

    @pytest.mark.integration
    def test_toggle_monitor_sets_owner(self, authenticated_client, test_user, db):
        s = self._make_strategy()
        resp = authenticated_client.post(f"/api/strategies/{s.id}/monitor/", {"active": True}, format="json")
        assert resp.status_code == 200 and resp.data["is_monitored"] is True
        s.refresh_from_db()
        assert s.owner_id == test_user.id

        off = authenticated_client.post(f"/api/strategies/{s.id}/monitor/", {"active": False}, format="json")
        assert off.data["is_monitored"] is False
        s.refresh_from_db()
        assert s.owner_id is None

    @pytest.mark.integration
    def test_signal_endpoint(self, authenticated_client, db, monkeypatch):
        s = self._make_strategy()
        monkeypatch.setattr(
            "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
            lambda symbol, interval="1d", limit=200, **kw: OhlcvFetchResult(df=_df(), source="binance"),
        )
        resp = authenticated_client.get(f"/api/strategies/{s.id}/signal/")
        assert resp.status_code == 200
        assert resp.data["signal"] == "BUY"  # RSI < 85 → entrada activa
        assert resp.data["asset_symbol"] == "BTC"

    @pytest.mark.integration
    def test_evaluate_notifies_on_signal_change(self, db, test_user, monkeypatch, settings):
        from django.core import mail
        from core.infrastructure.persistence.models import StrategyDefinition
        from core.application.use_cases.monitor_strategies import EvaluateMonitoredStrategiesUseCase

        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        s = self._make_strategy()
        s.is_monitored = True
        s.owner = test_user
        s.last_signal = "HOLD"
        s.save()

        monkeypatch.setattr(
            "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
            lambda symbol, interval="1d", limit=200, **kw: OhlcvFetchResult(df=_df(), source="binance"),
        )
        result = EvaluateMonitoredStrategiesUseCase().execute()
        assert result["evaluated"] == 1
        assert result["notified"] == 1            # HOLD → BUY dispara notificación
        assert len(mail.outbox) == 1
        s.refresh_from_db()
        assert s.last_signal == "BUY"

        # Segunda evaluación: la señal no cambia → no se vuelve a notificar
        mail.outbox.clear()
        again = EvaluateMonitoredStrategiesUseCase().execute()
        assert again["notified"] == 0
        assert len(mail.outbox) == 0
