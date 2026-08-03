"""
test_incubation.py — Puerta de incubación antes del capital real (G5).

Un backtest, por bien validado que esté, mide el pasado. La única evidencia que
el sobreajuste no puede falsear es la que llega DESPUÉS de fijar la estrategia,
sobre datos que no existían cuando se tomó la decisión.

Estos tests fijan que no se puede poner dinero real detrás de una cartera sin
esa evidencia, y que cortar la exposición nunca se bloquea.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from core.domain.services import incubation


def _facts(days=30.0, trades=10, pnl=100.0, decayed=False):
    return incubation.IncubationFacts(
        days_running=days, trades_count=trades, realized_pnl=pnl, decayed=decayed,
    )


class TestPolicy:

    @pytest.mark.unit
    def test_mature_account_is_incubated(self):
        out = incubation.evaluate(_facts())
        assert out["incubated"] is True
        assert out["missing"] == []
        assert "superada" in out["note"]

    @pytest.mark.unit
    def test_too_recent_is_not_incubated(self):
        out = incubation.evaluate(_facts(days=3.0))
        assert out["incubated"] is False
        assert out["missing"] == ["min_days"]
        assert out["days_remaining"] == pytest.approx(11.0)

    @pytest.mark.unit
    def test_too_few_trades_is_not_incubated(self):
        out = incubation.evaluate(_facts(trades=1))
        assert out["missing"] == ["min_trades"]
        assert out["trades_remaining"] == 4

    @pytest.mark.unit
    def test_a_decayed_strategy_never_reaches_real_money(self):
        """Si se ha degradado en vivo, el tiempo cumplido no la rehabilita."""
        out = incubation.evaluate(_facts(days=200.0, trades=99, decayed=True))
        assert out["incubated"] is False
        assert "not_decayed" in out["missing"]

    @pytest.mark.unit
    def test_the_note_says_exactly_what_is_missing(self):
        """Un «no» sin explicación empuja a buscar cómo saltárselo; un plazo
        concreto lo convierte en espera."""
        out = incubation.evaluate(_facts(days=2.0, trades=1))
        assert "días de simulado" in out["note"]
        assert "operaciones" in out["note"]

    @pytest.mark.unit
    def test_profitability_is_optional_by_default(self):
        """Perder en simulado no impide incubar por defecto: la evidencia que
        se exige es de funcionamiento, no de acierto."""
        assert incubation.evaluate(_facts(pnl=-50.0))["incubated"] is True
        strict = incubation.IncubationPolicy(require_profitable=True)
        assert incubation.evaluate(_facts(pnl=-50.0), strict)["incubated"] is False


@pytest.fixture
def account(db, test_user):
    from core.infrastructure.persistence.models import (
        CryptoAsset, PaperTradingAccount, StrategyDefinition,
    )
    asset = CryptoAsset.objects.create(symbol="BTC", name="Bitcoin", current_price=100)
    strategy = StrategyDefinition.objects.create(
        asset=asset, name="RSI reversal", spec_hash="abc", interval="1d",
        passed_gating=True, status="validated",
        spec={
            "entry": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14},
                 "op": "lt", "threshold": 30.0}]},
            "exit": {"combine": "AND", "conditions": [
                {"type": "threshold", "indicator": "RSI", "params": {"window": 14},
                 "op": "gt", "threshold": 70.0}]},
        },
    )
    return PaperTradingAccount.objects.create(
        strategy=strategy, owner=test_user, asset_symbol="BTC", interval="1d",
        cash=1000.0, initial_capital=1000.0,
    )


@pytest.fixture
def connection(db, test_user):
    from core.infrastructure.security.crypto import encrypt_secret
    from core.infrastructure.persistence.models import ExchangeConnection
    return ExchangeConnection.objects.create(
        owner=test_user, exchange="binance",
        api_key_enc=encrypt_secret("K"), api_secret_enc=encrypt_secret("S"),
    )


class TestPromotionEndpoint:

    @pytest.mark.integration
    def test_fresh_account_cannot_go_live(self, authenticated_client, account, connection):
        resp = authenticated_client.post(
            f"/api/strategies/paper/{account.id}/live/",
            {"enable": True, "connection_id": connection.id}, format="json",
        )

        assert resp.status_code == 409
        assert resp.data["blocked_by"] == "incubation"
        assert "min_days" in resp.data["incubation"]["missing"]

        account.refresh_from_db()
        assert account.live_enabled is False        # y no se activó a medias

    @pytest.mark.integration
    def test_incubated_account_can_go_live(self, authenticated_client, account, connection):
        from core.infrastructure.persistence.models import PaperTradingAccount

        PaperTradingAccount.objects.filter(id=account.id).update(
            started_at=timezone.now() - timedelta(days=30), trades_count=12,
        )

        resp = authenticated_client.post(
            f"/api/strategies/paper/{account.id}/live/",
            {"enable": True, "connection_id": connection.id}, format="json",
        )

        assert resp.status_code == 200
        assert resp.data["live_enabled"] is True
        assert resp.data["incubation"]["incubated"] is True

    @pytest.mark.integration
    def test_disabling_is_never_blocked(self, authenticated_client, account):
        """Cortar la exposición siempre está permitido, incubada o no."""
        resp = authenticated_client.post(
            f"/api/strategies/paper/{account.id}/live/", {"enable": False}, format="json",
        )
        assert resp.status_code == 200
        assert resp.data["live_enabled"] is False
