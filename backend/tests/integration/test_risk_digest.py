"""
tests/integration/test_risk_digest.py — Resumen diario de riesgo por email.
"""

from datetime import datetime, timezone as tz

import pytest
from django.core import mail


def _user(django_user_model, email, risk_digest=True, verified=True):
    u = django_user_model.objects.create_user(email=email, username=email.split("@")[0], password="x")
    u.is_email_verified = verified
    u.notify_risk_digest = risk_digest
    u.save()
    return u


def _open_position(user, symbol="BTC", qty="0.5", price="60000"):
    from decimal import Decimal
    from core.infrastructure.persistence.models import CryptoAsset, Position
    asset, _ = CryptoAsset.objects.get_or_create(
        symbol=symbol, defaults={"name": symbol, "current_price": Decimal(price)})
    asset.current_price = Decimal(price)
    asset.save()
    Position.objects.create(
        user=user, asset=asset, direction="LONG", status="OPEN",
        avg_entry_price=Decimal(price), open_quantity=Decimal(qty),
        initial_quantity=Decimal(qty), opened_at=datetime(2026, 1, 1, tzinfo=tz.utc),
    )


class TestRiskDigest:

    @pytest.mark.integration
    def test_sends_only_to_subscribers_with_exposure(self, db, django_user_model):
        from core.application.use_cases.send_risk_digest import SendRiskDigestUseCase

        subbed = _user(django_user_model, "sub@e.com", risk_digest=True)
        _open_position(subbed)
        _user(django_user_model, "nosub@e.com", risk_digest=False)   # no suscrito
        empty = _user(django_user_model, "empty@e.com", risk_digest=True)  # sin posiciones

        mail.outbox.clear()
        sent = SendRiskDigestUseCase().execute()
        assert sent == 1
        assert len(mail.outbox) == 1
        msg = mail.outbox[0]
        assert msg.to == ["sub@e.com"]
        assert "riesgo" in msg.subject.lower()
        assert "Exposición" in msg.body
        assert empty.email not in [t for m in mail.outbox for t in m.to]

    @pytest.mark.integration
    def test_unverified_email_excluded(self, db, django_user_model):
        from core.application.use_cases.send_risk_digest import SendRiskDigestUseCase

        u = _user(django_user_model, "unv@e.com", risk_digest=True, verified=False)
        _open_position(u)
        mail.outbox.clear()
        assert SendRiskDigestUseCase().execute() == 0


class TestPreference:

    @pytest.mark.integration
    def test_toggle_via_me_endpoint(self, authenticated_client):
        resp = authenticated_client.get("/api/auth/me/")
        assert "notify_risk_digest" in resp.data and resp.data["notify_risk_digest"] is False
        patch = authenticated_client.patch("/api/auth/me/", {"notify_risk_digest": True}, format="json")
        assert patch.status_code == 200
        assert authenticated_client.get("/api/auth/me/").data["notify_risk_digest"] is True
