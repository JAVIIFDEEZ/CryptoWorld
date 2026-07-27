"""
tests/integration/test_wallet_dossier.py — Dossier de inteligencia de wallet.

Verifica el cruce completo con un cliente Blockscout simulado: contrapartes
agregadas con etiquetado de exchanges, lectura de comportamiento, cruce con el
histórico propio de ballenas, presencia multi-cadena, degradación parcial y el
endpoint con su validación.
"""

from datetime import datetime, timezone as tz

import pytest

from core.application.use_cases.wallet_dossier import WalletDossierUseCase

ADDR = "0x" + "a" * 40
WHALE = "0x" + "b" * 40
BINANCE = "0x" + "c" * 40


class _FakeClient:
    """Cliente Blockscout falso: la wallet opera con Binance y con otra wallet."""

    def __init__(self, fail_profile=False):
        self.fail_profile = fail_profile

    def get_address(self, chain, address):
        if self.fail_profile and chain == "ethereum":
            raise RuntimeError("perfil caído")
        if chain == "base":   # presencia multi-cadena: existe en base
            return {"coin_balance": str(int(2.5e18)), "transactions_count": "12"}
        if chain != "ethereum":
            return {"coin_balance": "0", "transactions_count": "0"}
        return {"coin_balance": str(int(10e18)), "exchange_rate": "2000",
                "transactions_count": "150", "is_contract": False, "name": None}

    def get_transactions(self, chain, address):
        def tx(frm, to, eth, name=None):
            return {"from": {"hash": frm, "name": name if frm != ADDR else None},
                    "to": {"hash": to, "name": name if to != ADDR else None},
                    "value": str(int(eth * 1e18))}
        return [
            tx(BINANCE, ADDR, 5.0, name="Binance 14"),   # retirada de exchange
            tx(BINANCE, ADDR, 3.0, name="Binance 14"),   # retirada de exchange
            tx(ADDR, BINANCE, 1.0, name="Binance 14"),   # depósito
            tx(ADDR, WHALE, 2.0),                        # envío a wallet anónima
            tx(WHALE, ADDR, 0.5),
        ]


@pytest.fixture
def whale_snapshots(db):
    from core.infrastructure.persistence.models import WhaleMovementSnapshot
    WhaleMovementSnapshot.objects.create(
        chain="ethereum", symbol="ETH", amount=100.0, value_usd=200000.0,
        from_address=ADDR, to_address=BINANCE, from_label="", to_label="Binance",
        direction="to_exchange", tx_hash="0x1",
        moved_at=datetime(2026, 7, 1, tzinfo=tz.utc),
    )
    WhaleMovementSnapshot.objects.create(
        chain="ethereum", symbol="ETH", amount=50.0, value_usd=100000.0,
        from_address=BINANCE, to_address=ADDR, from_label="Binance", to_label="",
        direction="from_exchange", tx_hash="0x2",
        moved_at=datetime(2026, 7, 2, tzinfo=tz.utc),
    )


class TestDossier:

    @pytest.mark.integration
    def test_full_dossier_crosses_all_sources(self, db, whale_snapshots):
        out = WalletDossierUseCase(client=_FakeClient()).execute("ethereum", ADDR)
        assert not out.get("error") and out["partial"] is False
        # Perfil valorado en USD
        assert out["profile"]["balance_native"] == 10.0
        assert out["profile"]["balance_usd"] == 20000.0
        # Contrapartes: Binance etiquetado como exchange y agregado (3 txs)
        binance = next(c for c in out["counterparties"] if c["is_exchange"])
        assert binance["txs"] == 3 and binance["label"] == "Binance 14"
        assert binance["received_native"] == 8.0 and binance["sent_native"] == 1.0
        # Comportamiento: retira más de lo que deposita → ACUMULA
        b = out["behavior"]
        assert b["withdrawals_from_exchange"] == 2 and b["deposits_to_exchange"] == 1
        assert b["reading"].startswith("ACUMULA")
        # Cruce con histórico propio del escáner
        wh = out["whale_history"]
        assert wh["appearances"] == 2 and wh["total_usd"] == 300000.0
        assert wh["as_sender"] == 1 and wh["as_receiver"] == 1
        # Presencia multi-cadena: aparece en base con saldo
        chains = {m["chain"] for m in out["multichain"]}
        assert "base" in chains and "ethereum" not in chains

    @pytest.mark.integration
    def test_partial_degradation_on_profile_failure(self, db):
        out = WalletDossierUseCase(client=_FakeClient(fail_profile=True)).execute("ethereum", ADDR)
        assert out["partial"] is True
        assert out["profile"] == {}
        assert len(out["counterparties"]) >= 1   # el resto sigue funcionando

    @pytest.mark.integration
    def test_invalid_inputs(self, db):
        uc = WalletDossierUseCase(client=_FakeClient())
        assert "error" in uc.execute("dogechain", ADDR)
        assert "error" in uc.execute("ethereum", "no-es-una-dirección")


class TestApi:

    @pytest.mark.integration
    def test_requires_auth(self, api_client):
        assert api_client.get("/api/blockchain/wallet/dossier/").status_code == 401

    @pytest.mark.integration
    def test_requires_address(self, authenticated_client):
        resp = authenticated_client.get("/api/blockchain/wallet/dossier/")
        assert resp.status_code == 400 and "address" in resp.data["error"]
