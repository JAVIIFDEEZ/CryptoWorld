"""
tests/unit/domain/test_token_safety.py — Seguridad de token (dominio puro).

Verifica la detección de poderes peligrosos (ABI/fuente), el efecto del
ownership renunciado, el proxy, la falta de verificación y la combinación con
la concentración de tenedores.
"""

import pytest

from core.domain.services import token_safety as ts


def _fn(name):
    return {"type": "function", "name": name}


class TestPowerDetection:

    @pytest.mark.unit
    def test_detects_mint_and_blacklist_from_abi(self):
        abi = [_fn("mint"), _fn("setBlacklist"), _fn("transfer")]
        out = ts.analyze_token_safety({"is_verified": True, "owner": "0xowner", "abi": abi})
        cats = {f["category"] for f in out["flags"]}
        assert "mint" in cats and "blacklist" in cats
        assert out["verdict"] in ("PELIGROSO", "RIESGO ALTO")

    @pytest.mark.unit
    def test_detects_from_source_when_no_abi(self):
        src = "function setSellTax(uint256 t) external onlyOwner { ... }"
        out = ts.analyze_token_safety(
            {"is_verified": True, "owner": "0xowner", "abi": None, "source_code": src})
        assert any(f["category"] == "setfee" for f in out["flags"])
        assert out["flags"][0]["source"] in ("abi", "source")


class TestOwnershipAndProxy:

    @pytest.mark.unit
    def test_renounced_ownership_disables_powers(self):
        abi = [_fn("mint"), _fn("pause")]
        zero = "0x0000000000000000000000000000000000000000"
        out = ts.analyze_token_safety({"is_verified": True, "owner": zero, "abi": abi})
        assert out["ownership_renounced"] is True
        # Poderes desactivados: no aparecen mint/pause como banderas
        cats = {f["category"] for f in out["flags"]}
        assert "mint" not in cats and "pause" not in cats
        assert any("renunciada" in g for g in out["green_flags"])

    @pytest.mark.unit
    def test_proxy_flagged(self):
        out = ts.analyze_token_safety(
            {"is_verified": True, "owner": "0xowner", "is_proxy": True, "abi": []})
        assert out["is_proxy"] is True
        assert any(f["category"] == "proxy" for f in out["flags"])

    @pytest.mark.unit
    def test_unverified_is_penalized(self):
        out = ts.analyze_token_safety({"is_verified": False, "abi": None})
        assert out["verified"] is False
        assert any(f["category"] == "unverified" for f in out["flags"])
        assert out["score"] >= 35


class TestConcentrationCombination:

    @pytest.mark.unit
    def test_critical_concentration_adds_risk(self):
        base = ts.analyze_token_safety({"is_verified": True, "owner": "0xo", "abi": []})
        withc = ts.analyze_token_safety(
            {"is_verified": True, "owner": "0xo", "abi": []},
            concentration={"available": True, "top10_share_pct": 80})
        assert withc["score"] > base["score"]
        assert withc["top10_concentration_pct"] == 80
        assert any(f["category"] == "concentration" for f in withc["flags"])

    @pytest.mark.unit
    def test_safe_token_is_reasonable(self):
        # Verificado, propiedad renunciada, sin poderes, base amplia → RAZONABLE
        zero = "0x0000000000000000000000000000000000000000"
        out = ts.analyze_token_safety(
            {"is_verified": True, "owner": zero, "abi": [_fn("transfer"), _fn("approve")]},
            concentration={"available": True, "top10_share_pct": 12})
        assert out["verdict"] == "RAZONABLE"
        assert out["score"] < 25
        assert len(out["green_flags"]) >= 2

    @pytest.mark.unit
    def test_score_capped_at_100(self):
        abi = [_fn(n) for n in ("mint", "blacklist", "pause", "setFee", "setMaxTx", "setTaxWallet")]
        out = ts.analyze_token_safety(
            {"is_verified": False, "owner": "0xo", "is_proxy": True, "abi": abi},
            concentration={"available": True, "top10_share_pct": 90})
        assert out["score"] == 100
        assert out["verdict"] == "PELIGROSO"
