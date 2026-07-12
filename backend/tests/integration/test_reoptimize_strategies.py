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
    def test_explicit_pairs_override_tracked(self, assets, monkeypatch):
        # Reoptimización dirigida de un activo concreto (p. ej. decaído), sin
        # depender de que esté "seguido".
        captured = {}
        fake_report = {
            "summary": {"passed_gating": 1, "candidates_gated": 3},
            "ranking": [
                {"spec_hash": "fresh", "passed_gating": True, "rank": 1, "fitness": 1.1,
                 "description": "nueva", "spec": _spec(), "gating": {"metrics": {}, "checks": {}},
                 "holdout_validation": {"return_pct": 9}},
            ],
        }

        def _fake(self, **kw):
            captured["symbol"] = kw.get("asset_symbol")
            return fake_report

        monkeypatch.setattr(
            "core.application.use_cases.generate_strategies.GenerateStrategiesUseCase.execute", _fake,
        )
        out = ReoptimizeStrategiesUseCase().execute(pairs=[("ETH", "4h")])
        assert captured["symbol"] == "ETH"
        assert out["pairs"] == 1 and out["new_strategies"] == 1

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


class TestFillStrategyStable:
    """Establo nocturno: solo genera para los huecos, con tope por pasada."""

    @pytest.mark.integration
    def test_only_gaps_are_generated_with_cap(self, assets, test_user, monkeypatch):
        from django.utils import timezone
        from core.infrastructure.persistence.models import CryptoAsset, UserWatchlist
        from core.application.use_cases.reoptimize_strategies import (
            FillStrategyStableUseCase, ReoptimizeStrategiesUseCase,
        )

        # Universo: BTC/ETH (fixture) + SOL y ADA en watchlist del usuario
        sol = CryptoAsset.objects.create(symbol="SOL", name="Solana")
        ada = CryptoAsset.objects.create(symbol="ADA", name="Cardano")
        for a in (sol, ada):
            UserWatchlist.objects.create(user=test_user, asset=a)

        # BTC ya está cubierto: estrategia validada FRESCA
        s = _strategy(assets["BTC"], fitness=1.0, spec_hash="fresh-btc")
        s.generated_at = timezone.now()
        s.save(update_fields=["generated_at"])

        called = {}
        def fake_execute(self, preset="balanced", limit_pairs=12, pairs=None):
            called["pairs"] = pairs
            return {"new_strategies": len(pairs or []), "regenerated": len(pairs or []),
                    "details": [], "pairs": len(pairs or [])}
        monkeypatch.setattr(ReoptimizeStrategiesUseCase, "execute", fake_execute)

        out = FillStrategyStableUseCase().execute(per_night=2, top_assets=0)
        # Universo = watchlist {SOL, ADA}; BTC cubierto no cuenta como hueco
        assert out["gaps"] == 2
        assert sorted(out["generated_for"]) == ["ADA", "SOL"]
        assert [p for p in called["pairs"]] == [("ADA", "1d"), ("SOL", "1d")]
        assert out["new_strategies"] == 2

    @pytest.mark.integration
    def test_covered_universe_generates_nothing(self, assets, monkeypatch):
        from django.utils import timezone
        from core.application.use_cases.reoptimize_strategies import (
            FillStrategyStableUseCase, ReoptimizeStrategiesUseCase,
        )
        # Todo el universo (solo BTC vía top_assets=1... usamos watchlist vacía y
        # top_assets=0 ⇒ universo vacío) — y con BTC cubierto tampoco genera.
        s = _strategy(assets["BTC"], fitness=1.0, spec_hash="fresh-btc-2")
        s.generated_at = timezone.now()
        s.save(update_fields=["generated_at"])

        def boom(self, **kw):  # noqa: ARG001
            raise AssertionError("No debería regenerarse nada")
        monkeypatch.setattr(ReoptimizeStrategiesUseCase, "execute", boom)

        out = FillStrategyStableUseCase().execute(per_night=2, top_assets=0)
        assert out["gaps"] == 0 and out["new_strategies"] == 0

    @pytest.mark.integration
    def test_stale_strategy_counts_as_gap(self, assets, monkeypatch):
        from datetime import timedelta
        from django.utils import timezone
        from core.infrastructure.persistence.models import UserWatchlist
        from core.application.use_cases.reoptimize_strategies import (
            FillStrategyStableUseCase, ReoptimizeStrategiesUseCase,
        )
        # BTC tiene estrategia validada pero RANCIA (45 días) ⇒ es hueco
        s = _strategy(assets["BTC"], fitness=1.0, spec_hash="stale-btc")
        s.generated_at = timezone.now() - timedelta(days=45)
        s.save(update_fields=["generated_at"])

        called = {}
        def fake_execute(self, preset="balanced", limit_pairs=12, pairs=None):
            called["pairs"] = pairs
            return {"new_strategies": 1, "regenerated": 1, "details": [], "pairs": 1}
        monkeypatch.setattr(ReoptimizeStrategiesUseCase, "execute", fake_execute)

        from core.infrastructure.persistence.models import User
        u = User.objects.create_user(email="stable@test.com", username="stable", password="x12345678!")
        UserWatchlist.objects.create(user=u, asset=assets["BTC"])

        out = FillStrategyStableUseCase().execute(per_night=2, stale_days=30, top_assets=0)
        assert out["gaps"] == 1
        assert called["pairs"] == [("BTC", "1d")]
