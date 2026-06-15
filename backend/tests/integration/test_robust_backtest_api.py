"""
tests/integration/test_robust_backtest_api.py — Endpoints de la suite robusta.

Verifica el criterio de aceptación: el endpoint lanza la suite en Celery sin
bloquear y devuelve un job_id; el polling entrega el informe con el veredicto.
Se usa Celery en modo eager + un OHLCV sintético (sin red) y una config
reducida para que el test sea rápido.
"""

import math

import numpy as np
import pandas as pd
import pytest

import core.application.use_cases.run_robust_backtest as rrb
from core.application.use_cases.ohlcv_fetcher import OhlcvFetchResult


def _synthetic_df(n=300):
    closes = [100 + 0.15 * i + 12 * math.sin(2 * math.pi * i / 30) for i in range(n)]
    return pd.DataFrame({
        "timestamp": [1700000000000 + i * 86400000 for i in range(n)],
        "open": [c * 0.99 for c in closes], "high": [c * 1.02 for c in closes],
        "low": [c * 0.98 for c in closes], "close": closes, "volume": [1000.0] * n,
    })


@pytest.fixture
def celery_eager(monkeypatch):
    """
    Ejecuta la tarea en el proceso del test y guarda el resultado en el
    backend (Redis) para que AsyncResult(job_id) lo recupere igual que con
    un worker real. Se logra redirigiendo .delay() a .apply() (local +
    task_store_eager_result, activado en settings).
    """
    from core.tasks import run_robust_backtest as task

    monkeypatch.setattr(
        task, "delay",
        lambda *args, **kwargs: task.apply(args=args, kwargs=kwargs),
    )
    yield


@pytest.fixture
def fast_suite(monkeypatch):
    """OHLCV sintético + presupuesto de cómputo reducido (sin red, rápido)."""
    monkeypatch.setattr(
        "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
        lambda symbol, interval="1d", limit=365, **kw: OhlcvFetchResult(df=_synthetic_df(), source="binance"),
    )
    real_suite = rrb.run_robustness_suite

    def small(df, strategy, interval="1d", initial_capital=10000.0, config=None):
        cfg = rrb.RobustnessConfig(n_trials=6, wf_splits=2, wf_trials=4, n_perms=10, n_sims=80)
        return real_suite(df, strategy, interval=interval, initial_capital=initial_capital, config=cfg)

    monkeypatch.setattr(rrb, "run_robustness_suite", small)


class TestRobustBacktestApi:

    @pytest.mark.integration
    def test_requires_authentication(self, api_client):
        resp = api_client.post("/api/analysis/backtest/robust/", {}, format="json")
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_invalid_strategy_returns_400(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/analysis/backtest/robust/",
            {"asset_symbol": "BTC", "strategy": "no_existe"},
            format="json",
        )
        assert resp.status_code == 400

    @pytest.mark.integration
    def test_launch_then_poll_returns_report(self, authenticated_client, celery_eager, fast_suite):
        # 1. Lanzar: devuelve job_id sin bloquear
        launch = authenticated_client.post(
            "/api/analysis/backtest/robust/",
            {"asset_symbol": "BTC", "strategy": "rsi_reversal", "interval": "1d"},
            format="json",
        )
        assert launch.status_code == 202
        job_id = launch.data["job_id"]
        assert job_id

        # 2. Poll: entrega el informe completo con el veredicto
        status = authenticated_client.get(f"/api/analysis/backtest/robust/{job_id}/")
        assert status.status_code == 200
        assert status.data["status"] == "SUCCESS"

        report = status.data["result"]
        assert report["verdict"] in ("ROBUSTA", "FRÁGIL", "SOBREAJUSTADA")
        assert 0 <= report["robustness_score"] <= 100
        assert "metrics" in report and "diagnostics" in report
        d = report["diagnostics"]
        for key in ("deflated_sharpe", "pbo", "walk_forward_anchored",
                    "monte_carlo", "permutation", "lookahead", "recursive_instability"):
            assert key in d
        assert "charts" in report

    @pytest.mark.integration
    def test_insufficient_candles_reports_error(self, authenticated_client, celery_eager, monkeypatch):
        monkeypatch.setattr(
            "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
            lambda symbol, interval="1d", limit=365, **kw: OhlcvFetchResult(df=_synthetic_df(100), source="binance"),
        )
        launch = authenticated_client.post(
            "/api/analysis/backtest/robust/",
            {"asset_symbol": "BTC", "strategy": "rsi_reversal"},
            format="json",
        )
        assert launch.status_code == 202
        status = authenticated_client.get(f"/api/analysis/backtest/robust/{launch.data['job_id']}/")
        assert "error" in status.data["result"]
