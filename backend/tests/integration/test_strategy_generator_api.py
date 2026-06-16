"""
tests/integration/test_strategy_generator_api.py — Endpoint del generador.

Verifica el criterio de aceptación: POST /api/strategies/generate/ lanza el
generador genético en Celery sin bloquear y devuelve un job_id; el polling
entrega el informe con el ranking de finalistas robustos, y estos quedan
persistidos como StrategyDefinition. Celery en modo eager + OHLCV sintético
(sin red) + config reducida para rapidez.
"""

import numpy as np
import pandas as pd
import pytest

import core.application.use_cases.generate_strategies as gs
from core.application.use_cases.ohlcv_fetcher import OhlcvFetchResult
from core.domain.services.strategy_generator import GAConfig
from core.domain.services.strategy_evaluation import GatingThresholds


def _synthetic_df(n=700, seed=42):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    price = 100 + 22 * np.sin(t / 22.0) + 6 * np.sin(t / 7.0) + rng.normal(0, 0.5, n)
    price = np.maximum(price, 5.0)
    return pd.DataFrame({
        "timestamp": (1_600_000_000 + t * 86400) * 1000,
        "open": price, "high": price + 0.3, "low": price - 0.3,
        "close": price, "volume": [1000.0] * n,
    })


@pytest.fixture
def celery_eager(monkeypatch):
    """Redirige .delay() a .apply() (local + task_store_eager_result)."""
    from core.tasks import generate_strategies as task
    monkeypatch.setattr(
        task, "delay",
        lambda *args, **kwargs: task.apply(args=args, kwargs=kwargs),
    )
    yield


@pytest.fixture
def fast_generator(monkeypatch):
    """OHLCV sintético + GA/gating reducido (sin red, rápido)."""
    monkeypatch.setattr(
        "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
        lambda symbol, interval="1d", limit=730, **kw: OhlcvFetchResult(df=_synthetic_df(), source="binance"),
    )
    real = gs.generate_strategies

    def small(df, interval="1d", config=None, initial_capital=10000.0):
        cfg = gs.GenerationConfig(
            holdout_fraction=0.2, top_k=3, max_gating_attempts=5,
            ga=GAConfig(population_size=18, generations=5, seed=7),
            gating=GatingThresholds(wf_splits=3, pbo_neighbors=6, mc_sims=120, min_trades=8),
        )
        return real(df, interval=interval, config=cfg, initial_capital=initial_capital)

    monkeypatch.setattr(gs, "generate_strategies", small)


class TestStrategyGeneratorApi:

    @pytest.mark.integration
    def test_requires_authentication(self, api_client):
        resp = api_client.post("/api/strategies/generate/", {}, format="json")
        assert resp.status_code == 401

    @pytest.mark.integration
    def test_missing_asset_returns_400(self, authenticated_client):
        resp = authenticated_client.post("/api/strategies/generate/", {}, format="json")
        assert resp.status_code == 400

    @pytest.mark.integration
    def test_launch_then_poll_returns_ranking(self, authenticated_client, celery_eager, fast_generator):
        # 1. Lanzar: job_id sin bloquear
        launch = authenticated_client.post(
            "/api/strategies/generate/",
            {"asset_symbol": "BTC", "interval": "1d", "preset": "fast"},
            format="json",
        )
        assert launch.status_code == 202
        job_id = launch.data["job_id"]
        assert job_id

        # 2. Poll: informe completo con ranking + partición + métricas de robustez
        status = authenticated_client.get(f"/api/strategies/generate/{job_id}/")
        assert status.status_code == 200
        assert status.data["status"] == "SUCCESS"

        report = status.data["result"]
        assert "ranking" in report and "data_partition" in report
        assert report["data_partition"]["holdout_candles"] > 0
        assert "ga_evolution" in report and "history" in report["ga_evolution"]
        # Si hay finalistas, traen métricas de robustez y validación holdout
        for f in report["ranking"]:
            assert all(f["gating"]["checks"].values())
            assert "pbo" in f["gating"]["metrics"]
            assert "holdout_validation" in f

    @pytest.mark.integration
    def test_finalists_are_persisted(self, authenticated_client, celery_eager, fast_generator, db):
        from core.infrastructure.persistence.models import StrategyDefinition

        before = StrategyDefinition.objects.count()
        launch = authenticated_client.post(
            "/api/strategies/generate/",
            {"asset_symbol": "BTC", "preset": "fast"},
            format="json",
        )
        job_id = launch.data["job_id"]
        report = authenticated_client.get(f"/api/strategies/generate/{job_id}/").data["result"]

        persisted = StrategyDefinition.objects.count() - before
        assert persisted == len(report["ranking"])
        if report["ranking"]:
            obj = StrategyDefinition.objects.order_by("-id").first()
            assert obj.passed_gating is True
            assert obj.spec and obj.robustness_metrics and obj.holdout_metrics

    @pytest.mark.integration
    def test_insufficient_candles_reports_error(self, authenticated_client, celery_eager, monkeypatch):
        monkeypatch.setattr(
            "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
            lambda symbol, interval="1d", limit=730, **kw: OhlcvFetchResult(df=_synthetic_df(120), source="binance"),
        )
        launch = authenticated_client.post(
            "/api/strategies/generate/", {"asset_symbol": "BTC"}, format="json",
        )
        assert launch.status_code == 202
        status = authenticated_client.get(f"/api/strategies/generate/{launch.data['job_id']}/")
        assert "error" in status.data["result"]


class TestSavedStrategiesList:

    @pytest.mark.integration
    def test_requires_authentication(self, api_client):
        assert api_client.get("/api/strategies/").status_code == 401

    @pytest.mark.integration
    def test_lists_only_passed_filtered_by_symbol(self, authenticated_client, db):
        from core.infrastructure.persistence.models import CryptoAsset, StrategyDefinition

        btc = CryptoAsset.objects.create(symbol="BTC", name="Bitcoin")
        eth = CryptoAsset.objects.create(symbol="ETH", name="Ethereum")
        spec = {"entry": {"combine": "AND", "conditions": []}, "exit": {"combine": "AND", "conditions": []}}
        StrategyDefinition.objects.create(asset=btc, name="BTC robusta", spec=spec, spec_hash="a", rank=1, passed_gating=True, status="validated")
        StrategyDefinition.objects.create(asset=eth, name="ETH robusta", spec=spec, spec_hash="b", rank=1, passed_gating=True, status="validated")
        StrategyDefinition.objects.create(asset=btc, name="BTC descartada", spec=spec, spec_hash="c", rank=0, passed_gating=False, status="rejected")

        resp = authenticated_client.get("/api/strategies/?asset_symbol=BTC")
        assert resp.status_code == 200
        names = [r["name"] for r in resp.data["results"]]
        assert names == ["BTC robusta"]  # solo la que pasó el gating y es de BTC

    @pytest.mark.integration
    def test_returns_full_payload(self, authenticated_client, db):
        from core.infrastructure.persistence.models import CryptoAsset, StrategyDefinition

        sol = CryptoAsset.objects.create(symbol="SOL", name="Solana")
        StrategyDefinition.objects.create(
            asset=sol, name="SOL robusta", spec={"entry": {}, "exit": {}}, spec_hash="z",
            rank=1, fitness=2.1, passed_gating=True,
            robustness_metrics={"pbo": 0.2}, holdout_metrics={"return_pct": 10.0}, status="validated",
        )
        resp = authenticated_client.get("/api/strategies/")
        row = resp.data["results"][0]
        for key in ("id", "spec", "spec_hash", "fitness", "robustness_metrics", "holdout_metrics", "created_at"):
            assert key in row


class TestPresets:

    @pytest.mark.unit
    def test_presets_scale_compute(self):
        from core.application.use_cases.generate_strategies import config_for_preset
        fast = config_for_preset("fast")
        thorough = config_for_preset("thorough")
        assert fast.ga.population_size < thorough.ga.population_size
        assert fast.ga.generations < thorough.ga.generations
        # preset desconocido cae al balanceado
        assert config_for_preset("xxx").ga.population_size == config_for_preset("balanced").ga.population_size
