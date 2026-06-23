"""
tests/integration/test_watchlist.py — Vigilancia de direcciones on-chain.

Verifica el alta/baja/listado de direcciones vigiladas y, sobre todo, la
detección de movimientos: la tarea de monitorización crea una alerta cuando el
saldo varía por encima del umbral. El cliente Blockscout se mockea.
"""

import pytest

from core.application.use_cases.watchlist import (
    AddWatchedAddressUseCase, MonitorWatchedAddressesUseCase,
    RemoveWatchedAddressUseCase, WatchlistUseCase,
)

VITALIK = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"


def _info(coin_balance_wei, exchange_rate="2000.0"):
    return {"coin_balance": str(coin_balance_wei), "exchange_rate": exchange_rate,
            "is_contract": False, "ens_domain_name": None}


class _Client:
    """Cliente falso con saldo configurable por llamada."""
    def __init__(self, info):
        self._info = info

    def get_address(self, chain, address):
        return self._info


class TestAddRemove:

    @pytest.mark.integration
    def test_add_stores_initial_balance(self, test_user):
        client = _Client(_info(5 * 10**18))   # 5 ETH
        r = AddWatchedAddressUseCase(client=client).execute(
            owner=test_user, chain="ethereum", address=VITALIK, label="Vitalik", threshold_pct=10,
        )
        assert "error" not in r
        assert r["last_balance"] == pytest.approx(5.0)
        assert r["last_value_usd"] == pytest.approx(10000.0)
        assert r["label"] == "Vitalik" and r["alert_threshold_pct"] == 10

    @pytest.mark.integration
    def test_duplicate_rejected(self, test_user):
        client = _Client(_info(10**18))
        uc = AddWatchedAddressUseCase(client=client)
        uc.execute(owner=test_user, chain="ethereum", address=VITALIK)
        r2 = uc.execute(owner=test_user, chain="ethereum", address=VITALIK)
        assert "error" in r2 and "watchlist" in r2["error"].lower()

    @pytest.mark.integration
    def test_invalid_address_and_chain_rejected(self, test_user):
        uc = AddWatchedAddressUseCase(client=_Client(_info(0)))
        assert "error" in uc.execute(owner=test_user, chain="ethereum", address="0xbad")
        assert "error" in uc.execute(owner=test_user, chain="dogechain", address=VITALIK)

    @pytest.mark.integration
    def test_remove(self, test_user):
        client = _Client(_info(10**18))
        added = AddWatchedAddressUseCase(client=client).execute(
            owner=test_user, chain="ethereum", address=VITALIK,
        )
        out = RemoveWatchedAddressUseCase().execute(owner=test_user, watch_id=added["id"])
        assert out["removed"] is True
        assert WatchlistUseCase().execute(owner=test_user)["count"] == 0

    @pytest.mark.integration
    def test_remove_other_user_not_found(self, test_user):
        assert "error" in RemoveWatchedAddressUseCase().execute(owner=test_user, watch_id=999999)


class TestMonitoring:

    def _watch(self, user, last_balance):
        from core.infrastructure.persistence.models import WatchedAddress
        return WatchedAddress.objects.create(
            owner=user, chain="ethereum", address=VITALIK, native_symbol="ETH",
            alert_threshold_pct=5.0, last_balance=last_balance, last_value_usd=last_balance * 2000,
        )

    @pytest.mark.integration
    def test_large_move_creates_alert(self, test_user):
        self._watch(test_user, last_balance=10.0)            # saldo previo 10 ETH
        client = _Client(_info(13 * 10**18))                 # ahora 13 ETH → +30%
        out = MonitorWatchedAddressesUseCase(client=client).execute()
        assert out["checked"] == 1 and out["alerts"] == 1

        from core.infrastructure.persistence.models import AddressAlert, WatchedAddress
        alert = AddressAlert.objects.get()
        assert alert.direction == "increase"
        assert alert.delta == pytest.approx(3.0) and alert.delta_pct == pytest.approx(30.0)
        # El saldo de referencia se actualiza para la próxima pasada
        assert WatchedAddress.objects.get().last_balance == pytest.approx(13.0)

    @pytest.mark.integration
    def test_small_move_no_alert(self, test_user):
        self._watch(test_user, last_balance=10.0)
        client = _Client(_info(int(10.2 * 10**18)))          # +2% < umbral 5%
        out = MonitorWatchedAddressesUseCase(client=client).execute()
        assert out["alerts"] == 0

    @pytest.mark.integration
    def test_decrease_creates_outgoing_alert(self, test_user):
        self._watch(test_user, last_balance=10.0)
        client = _Client(_info(int(8 * 10**18)))             # -20%
        MonitorWatchedAddressesUseCase(client=client).execute()
        from core.infrastructure.persistence.models import AddressAlert
        assert AddressAlert.objects.get().direction == "decrease"


class TestApi:

    @pytest.mark.integration
    def test_requires_auth(self, api_client):
        assert api_client.get("/api/blockchain/watchlist/").status_code == 401

    @pytest.mark.integration
    def test_add_list_and_delete_via_api(self, authenticated_client, monkeypatch):
        from core.infrastructure.external_apis.blockscout_client import BlockscoutClient
        monkeypatch.setattr(BlockscoutClient, "get_address", lambda self, c, a: _info(3 * 10**18))

        add = authenticated_client.post(
            "/api/blockchain/watchlist/",
            {"chain": "ethereum", "address": VITALIK, "label": "test"}, format="json",
        )
        assert add.status_code == 201
        wid = add.data["id"]

        lst = authenticated_client.get("/api/blockchain/watchlist/")
        assert lst.status_code == 200 and lst.data["count"] == 1 and "alerts" in lst.data

        dele = authenticated_client.delete(f"/api/blockchain/watchlist/{wid}/")
        assert dele.status_code == 200 and dele.data["removed"] is True

    @pytest.mark.integration
    def test_add_bad_address_returns_400(self, authenticated_client):
        resp = authenticated_client.post(
            "/api/blockchain/watchlist/", {"chain": "ethereum", "address": "nope"}, format="json",
        )
        assert resp.status_code == 400
