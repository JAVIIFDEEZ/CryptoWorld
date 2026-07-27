"""
tests/integration/test_strategy_dossier.py — Dossier de auditoría de estrategia.

Verifica que el dossier reúne identidad+ADN, evidencia almacenada, análisis
fresco (mockeando los datos) y el track record SOLO del usuario que lo pide,
y que sobrevive sin datos frescos (degradación honesta).
"""

from collections import namedtuple

import numpy as np
import pandas as pd
import pytest


def _df(n=400, seed=3):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    price = np.maximum(100 + 20 * np.sin(t / 20.0) + rng.normal(0, 0.5, n), 5.0)
    return pd.DataFrame({
        "timestamp": (1_600_000_000 + t * 86400) * 1000,
        "open": price, "high": price + 0.3, "low": price - 0.3,
        "close": price, "volume": [1000.0] * n,
    })


def _spec():
    return {
        "entry": {"combine": "AND", "conditions": [
            {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "lt", "threshold": 30.0}]},
        "exit": {"combine": "AND", "conditions": [
            {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "gt", "threshold": 70.0}]},
    }


@pytest.fixture
def strategy(db):
    from django.utils import timezone
    from core.infrastructure.persistence.models import CryptoAsset, StrategyDefinition
    asset = CryptoAsset.objects.create(symbol="BTC", name="Bitcoin")
    return StrategyDefinition.objects.create(
        asset=asset, name="Campeona test", spec=_spec(), spec_hash="dossier-hash-1",
        interval="1d", rank=1, fitness=1.23, passed_gating=True, status="validated",
        robustness_metrics={"sharpe": 1.5, "pbo": 0.2, "cross_consistency": 0.67},
        gating_checks={"min_trades": True, "no_lookahead": True},
        holdout_metrics={"return_pct": 14.2, "sharpe": 1.1},
        generated_at=timezone.now(),
    )


class TestUseCase:

    @pytest.mark.integration
    def test_dossier_sections(self, strategy, test_user, monkeypatch):
        from django.core.cache import cache
        from core.application.use_cases import ohlcv_fetcher
        from core.application.use_cases.get_strategy_dossier import GetStrategyDossierUseCase
        from core.infrastructure.persistence.models import PaperTradingAccount

        cache.delete(f"strategy_dossier_fresh:{strategy.id}")
        Fetched = namedtuple("Fetched", ["df", "source"])
        monkeypatch.setattr(ohlcv_fetcher, "fetch_ohlcv_dataframe",
                            lambda **kw: Fetched(_df(), "test"))
        PaperTradingAccount.objects.create(
            strategy=strategy, owner=test_user, asset_symbol="BTC", interval="1d",
            initial_capital=10_000.0, cash=10_500.0, units=0.0, realized_pnl=500.0,
        )

        d = GetStrategyDossierUseCase().execute(strategy.id, owner=test_user)
        assert d["status"] == "OK"
        # Identidad + ADN
        assert d["identity"]["spec_hash"] == "dossier-hash-1"
        assert d["identity"]["asset_symbol"] == "BTC"
        assert "RSI" in d["identity"]["description"]
        # Evidencia almacenada intacta
        assert d["stored_evidence"]["robustness_metrics"]["cross_consistency"] == 0.67
        assert d["stored_evidence"]["holdout_metrics"]["return_pct"] == 14.2
        # Análisis fresco con equity y matriz WF
        fresh = d["fresh_analysis"]
        assert fresh["available"] is True
        assert fresh["equity"]["equity"][0] == pytest.approx(1.0)
        assert fresh["walk_forward_matrix"]["total_folds"] > 0
        # Track record del usuario
        tr = d["track_record"]["accounts"]
        assert len(tr) == 1
        assert tr[0]["total_return_pct"] == pytest.approx(5.0)

    @pytest.mark.integration
    def test_track_record_is_owner_scoped(self, strategy, test_user, admin_user, monkeypatch):
        from core.application.use_cases import ohlcv_fetcher
        from core.application.use_cases.get_strategy_dossier import GetStrategyDossierUseCase
        from core.infrastructure.persistence.models import PaperTradingAccount

        monkeypatch.setattr(ohlcv_fetcher, "fetch_ohlcv_dataframe", lambda **kw: None)
        PaperTradingAccount.objects.create(
            strategy=strategy, owner=admin_user, asset_symbol="BTC", interval="1d",
            initial_capital=10_000.0, cash=11_000.0,
        )
        d = GetStrategyDossierUseCase().execute(strategy.id, owner=test_user)
        assert d["track_record"]["accounts"] == []          # la del admin no aparece

    @pytest.mark.integration
    def test_survives_without_fresh_data(self, strategy, test_user, monkeypatch):
        from django.core.cache import cache
        from core.application.use_cases import ohlcv_fetcher
        from core.application.use_cases.get_strategy_dossier import GetStrategyDossierUseCase

        cache.delete(f"strategy_dossier_fresh:{strategy.id}")
        monkeypatch.setattr(ohlcv_fetcher, "fetch_ohlcv_dataframe",
                            lambda **kw: (_ for _ in ()).throw(RuntimeError("sin red")))
        d = GetStrategyDossierUseCase().execute(strategy.id, owner=test_user)
        assert d["status"] == "OK"                          # el dossier vive igual
        assert d["fresh_analysis"]["available"] is False
        assert d["stored_evidence"]["robustness_metrics"]["sharpe"] == 1.5

    @pytest.mark.integration
    def test_unknown_strategy(self, db, test_user):
        from core.application.use_cases.get_strategy_dossier import GetStrategyDossierUseCase
        assert "error" in GetStrategyDossierUseCase().execute(999_999, owner=test_user)


class TestApi:

    @pytest.mark.integration
    def test_requires_auth(self, api_client, strategy):
        assert api_client.get(f"/api/strategies/{strategy.id}/dossier/").status_code == 401

    @pytest.mark.integration
    def test_endpoint_returns_dossier(self, authenticated_client, strategy, monkeypatch):
        from core.application.use_cases import ohlcv_fetcher
        monkeypatch.setattr(ohlcv_fetcher, "fetch_ohlcv_dataframe", lambda **kw: None)
        resp = authenticated_client.get(f"/api/strategies/{strategy.id}/dossier/")
        assert resp.status_code == 200
        assert resp.data["identity"]["spec_hash"] == "dossier-hash-1"

    @pytest.mark.integration
    def test_endpoint_404(self, authenticated_client, db):
        assert authenticated_client.get("/api/strategies/999999/dossier/").status_code == 404
