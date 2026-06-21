"""
tests/integration/test_reoptimize_strategies.py — Reoptimización programada y
mejor estrategia por activo.

Verifica que la reoptimización solo toca los activos seguidos, deduplica por
spec_hash, y que la campeona de cada activo es la de mayor fitness con su track
record en vivo.
"""

import pytest

from core.application.use_cases.reoptimize_strategies import (
    BestStrategiesUseCase, ReoptimizeStrategiesUseCase, _tracked_pairs,
)


@pytest.fixture
def assets(db):
    from core.infrastructure.persistence.models import CryptoAsset
    return {
        "BTC": CryptoAsset.objects.create(symbol="BTC", name="Bitcoin"),
        "ETH": CryptoAsset.objects.create(symbol="ETH", name="Ethereum"),
    }


def _spec(threshold=30.0):
    return {
        "entry": {"combine": "AND", "conditions": [
            {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "lt", "threshold": threshold}]},
        "exit": {"combine": "AND", "conditions": [
            {"type": "threshold", "indicator": "RSI", "params": {"window": 14}, "op": "gt", "threshold": 70.0}]},
    }


def _strategy(asset, fitness, spec_hash, interval="1d", passed=True, holdout=None):
    from core.infrastructure.persistence.models import StrategyDefinition
    return StrategyDefinition.objects.create(
        asset=asset, name=f"S {spec_hash}", spec=_spec(), spec_hash=spec_hash, interval=interval,
        fitness=fitness, passed_gating=passed, status="validated",
        holdout_metrics=holdout or {"return_pct": 12.0, "sharpe": 1.2},
    )


class TestTrackedPairs:

    @pytest.mark.integration
    def test_only_followed_assets_are_tracked(self, assets):
        from core.infrastructure.persistence.models import PaperTradingAccount
        btc = _strategy(assets["BTC"], 1.5, "h_btc")
        # Paper trading activo sobre BTC
        PaperTradingAccount.objects.create(
            strategy=btc, asset_symbol="BTC", interval="1d", initial_capital=10000, cash=10000,
        )
        # ETH monitorizada
        eth = _strategy(assets["ETH"], 1.2, "h_eth")
        eth.is_monitored = True
        eth.save(update_fields=["is_monitored"])

        pairs = _tracked_pairs()
        assert ("BTC", "1d") in pairs and ("ETH", "1d") in pairs

    @pytest.mark.integration
    def test_untracked_assets_excluded(self, assets):
        _strategy(assets["BTC"], 1.5, "h_btc")  # guardada pero no seguida
        assert _tracked_pairs() == []


class TestBestStrategies:

    @pytest.mark.integration
    def test_champion_is_highest_fitness_per_asset(self, assets):
        _strategy(assets["BTC"], 1.0, "h1")
        _strategy(assets["BTC"], 2.5, "h2")     # campeona BTC
        _strategy(assets["ETH"], 1.8, "h3")     # campeona ETH

        out = BestStrategiesUseCase().execute()
        assert out["count"] == 2
        by_symbol = {r["asset_symbol"]: r for r in out["results"]}
        assert by_symbol["BTC"]["fitness"] == 2.5
        assert by_symbol["ETH"]["fitness"] == 1.8

    @pytest.mark.integration
    def test_includes_live_paper_track_record(self, assets, test_user):
        from core.infrastructure.persistence.models import PaperTradingAccount
        champ = _strategy(assets["BTC"], 2.0, "h1")
        PaperTradingAccount.objects.create(
            strategy=champ, owner=test_user, asset_symbol="BTC", interval="1d",
            initial_capital=10000, cash=11000, realized_pnl=1000, trades_count=3, wins=2,
        )
        out = BestStrategiesUseCase().execute(owner=test_user)
        live = out["results"][0]["live"]
        assert live is not None and live["realized_pnl"] == 1000 and live["trades_count"] == 3

    @pytest.mark.integration
    def test_only_passed_gating_considered(self, assets):
        _strategy(assets["BTC"], 9.0, "h_bad", passed=False)   # alto fitness pero no validada
        _strategy(assets["BTC"], 1.0, "h_good", passed=True)
        out = BestStrategiesUseCase().execute()
        assert out["count"] == 1 and out["results"][0]["fitness"] == 1.0

    @pytest.mark.integration
    def test_endpoint_requires_auth(self, api_client):
        assert api_client.get("/api/strategies/best/").status_code == 401

    @pytest.mark.integration
    def test_endpoint_returns_champions(self, authenticated_client, assets):
        _strategy(assets["BTC"], 1.0, "h1")
        resp = authenticated_client.get("/api/strategies/best/")
        assert resp.status_code == 200 and resp.data["count"] == 1


class TestReoptimize:

    @pytest.mark.integration
    def test_persists_only_new_spec_hashes(self, assets, monkeypatch):
        from core.infrastructure.persistence.models import PaperTradingAccount, StrategyDefinition
        # BTC seguido con una estrategia ya existente (spec_hash "old")
        existing = _strategy(assets["BTC"], 1.0, "old")
        PaperTradingAccount.objects.create(
            strategy=existing, asset_symbol="BTC", interval="1d", initial_capital=10000, cash=10000,
        )

        fake_report = {
            "summary": {"passed_gating": 2, "candidates_gated": 5},
            "ranking": [
                {"spec_hash": "old", "passed_gating": True, "rank": 1, "fitness": 1.0,
                 "description": "ya existe", "spec": _spec(),
                 "gating": {"metrics": {}, "checks": {}}, "holdout_validation": {"return_pct": 5}},
                {"spec_hash": "new", "passed_gating": True, "rank": 2, "fitness": 0.9,
                 "description": "nueva", "spec": _spec(31.0),
                 "gating": {"metrics": {}, "checks": {}}, "holdout_validation": {"return_pct": 8}},
            ],
        }
        monkeypatch.setattr(
            "core.application.use_cases.generate_strategies.GenerateStrategiesUseCase.execute",
            lambda self, **kw: fake_report,
        )
        out = ReoptimizeStrategiesUseCase().execute()
        assert out["regenerated"] == 1
        assert out["new_strategies"] == 1   # solo "new" se persiste, "old" se deduplica
        assert StrategyDefinition.objects.filter(asset=assets["BTC"], spec_hash="new").exists()
        assert StrategyDefinition.objects.filter(asset=assets["BTC"]).count() == 2

    @pytest.mark.integration
    def test_skips_assets_with_generation_error(self, assets, monkeypatch):
        from core.infrastructure.persistence.models import PaperTradingAccount
        s = _strategy(assets["BTC"], 1.0, "old")
        PaperTradingAccount.objects.create(
            strategy=s, asset_symbol="BTC", interval="1d", initial_capital=10000, cash=10000,
        )
        monkeypatch.setattr(
            "core.application.use_cases.generate_strategies.GenerateStrategiesUseCase.execute",
            lambda self, **kw: {"error": "insuficientes datos"},
        )
        out = ReoptimizeStrategiesUseCase().execute()
        assert out["regenerated"] == 0 and out["new_strategies"] == 0
