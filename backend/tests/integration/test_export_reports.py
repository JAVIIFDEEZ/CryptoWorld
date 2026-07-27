"""
tests/integration/test_export_reports.py — Exportación de informes CSV.
"""

from datetime import datetime, timezone as tz
from decimal import Decimal

import pytest


def _position(user, symbol="BTC", qty="0.5", price="60000", direction="LONG"):
    from core.infrastructure.persistence.models import CryptoAsset, Position
    asset, _ = CryptoAsset.objects.get_or_create(
        symbol=symbol, defaults={"name": symbol, "current_price": Decimal(price)})
    asset.current_price = Decimal(price); asset.save()
    Position.objects.create(
        user=user, asset=asset, direction=direction, status="OPEN",
        avg_entry_price=Decimal("50000"), open_quantity=Decimal(qty),
        initial_quantity=Decimal(qty), opened_at=datetime(2026, 1, 1, tzinfo=tz.utc))


class TestExport:

    @pytest.mark.integration
    def test_requires_auth(self, api_client):
        assert api_client.get("/api/portfolio/export/?type=positions").status_code == 401

    @pytest.mark.integration
    def test_positions_csv_download(self, authenticated_client, test_user):
        _position(test_user)
        resp = authenticated_client.get("/api/portfolio/export/?type=positions")
        assert resp.status_code == 200
        assert resp["Content-Type"].startswith("text/csv")
        assert "attachment" in resp["Content-Disposition"] and ".csv" in resp["Content-Disposition"]
        body = resp.content.decode()
        assert "symbol,direction,status" in body
        assert "BTC,LONG,OPEN" in body
        # unrealized = 0.5 * (60000 - 50000) = 5000
        assert "5000" in body

    @pytest.mark.integration
    def test_risk_csv_has_blocks(self, authenticated_client, test_user):
        _position(test_user)
        resp = authenticated_client.get("/api/portfolio/export/?type=risk")
        assert resp.status_code == 200
        body = resp.content.decode()
        assert "# EXPOSICIÓN POR ACTIVO" in body
        assert "# RESUMEN DE RIESGO" in body
        assert "gross_usd" in body and "var_status" in body

    @pytest.mark.integration
    def test_unknown_type_rejected(self, authenticated_client):
        assert authenticated_client.get("/api/portfolio/export/?type=xxx").status_code == 400

    @pytest.mark.integration
    def test_domain_positions_export_isolated_per_user(self, db, django_user_model):
        from core.application.use_cases.export_reports import export_positions_csv
        a = django_user_model.objects.create_user(email="a@e.com", username="a", password="x")
        b = django_user_model.objects.create_user(email="b@e.com", username="b", password="x")
        _position(a, symbol="ETH")
        out_b = export_positions_csv(b)
        assert "ETH" not in out_b   # b no ve las posiciones de a
