"""
tests/unit/domain/test_onchain_risk.py — Riesgo, aprobaciones y grafo de entidad.

Dominio puro y determinista: verifica la puntuación de riesgo (propia vs.
contrapartes vs. conducta), la clasificación de aprobaciones ERC-20 y la
agrupación por componentes conexos.
"""

import pytest

from core.domain.services import onchain_risk as r


class TestLabelRisk:

    @pytest.mark.unit
    def test_classifies_known_categories(self):
        assert r.classify_label_risk("Tornado Cash Router") == "mixer"
        assert r.classify_label_risk("OFAC SDN List") == "sanction"
        assert r.classify_label_risk("Fake_Phishing1234") == "phishing"
        assert r.classify_label_risk("Uniswap V3") is None
        assert r.classify_label_risk(None) is None


class TestAddressRiskScore:

    @pytest.mark.unit
    def test_self_flagged_dominates(self):
        out = r.address_risk_score(["Lazarus Group"], [], [], None)
        assert out["score"] >= 90 and out["band"] == "SEVERO"
        assert out["factors"][0]["kind"] == "self"

    @pytest.mark.unit
    def test_counterparty_exposure_accumulates_capped(self):
        cps = [{"address": f"0x{i}", "label": "Tornado Cash"} for i in range(5)]
        out = r.address_risk_score([], cps, [], None)
        assert out["flagged_counterparties"] == 5
        assert out["score"] <= 100
        # Sin tope, 5×38 = 190; con tope 60 → banda ALTO, no SEVERO por contrapartes solas
        assert out["band"] in ("ALTO", "MEDIO")

    @pytest.mark.unit
    def test_behavior_adds_to_counterparty_risk(self):
        cps = [{"address": "0xa", "label": "scam token"}]
        patterns = [{"type": "peel_chain", "note": "peel"}]
        out = r.address_risk_score([], cps, patterns, {"archetype": "Bot / automatizada"})
        # 32 (1 scam cp) + 15 (peel) + 5 (bot) = 52 → ALTO
        assert out["score"] == 52 and out["band"] == "ALTO"

    @pytest.mark.unit
    def test_clean_address_is_low(self):
        out = r.address_risk_score([], [{"address": "0xa", "label": "Uniswap"}], [], None)
        assert out["score"] == 0 and out["band"] == "BAJO"


class TestApprovals:

    @pytest.mark.unit
    def test_unlimited_unverified_is_high(self):
        level, _ = r.approval_risk(is_unlimited=True, spender_verified=False, spender_flag=None)
        assert level == "ALTO"

    @pytest.mark.unit
    def test_flagged_spender_is_severe(self):
        level, _ = r.approval_risk(is_unlimited=False, spender_verified=True, spender_flag="scam")
        assert level == "SEVERO"

    @pytest.mark.unit
    def test_analyze_keeps_latest_and_drops_revoked(self):
        approvals = [
            {"token": "0xT", "spender": "0xS", "amount": 1e40, "spender_verified": False},  # ilimitada
            {"token": "0xT", "spender": "0xS", "amount": 0.0, "spender_verified": False},   # revocada (más nueva)
            {"token": "0xU", "spender": "0xV", "amount": 100.0, "spender_verified": True},  # acotada
        ]
        out = r.analyze_approvals(approvals)
        # (0xT,0xS) queda revocada → excluida; solo queda la acotada
        assert out["total"] == 1
        assert out["approvals"][0]["risk"] == "BAJO"
        assert out["unlimited"] == 0

    @pytest.mark.unit
    def test_ranks_worst_first(self):
        approvals = [
            {"token": "0x1", "spender": "0xok", "amount": 50.0, "spender_verified": True},
            {"token": "0x2", "spender": "0xbad", "spender_label": "Drainer",
             "amount": None, "spender_verified": False},
            {"token": "0x3", "spender": "0xun", "amount": 1e40, "spender_verified": False},
        ]
        out = r.analyze_approvals(approvals)
        assert out["worst"] == "SEVERO"
        assert [it["risk"] for it in out["approvals"]] == ["SEVERO", "ALTO", "BAJO"]
        assert out["counts"]["SEVERO"] == 1


class TestEntityGraph:

    @pytest.mark.unit
    def test_connected_components_by_weight(self):
        nodes = ["a", "b", "c", "d"]
        edges = [{"a": "a", "b": "b", "weight": 3}, {"a": "c", "b": "d", "weight": 1}]
        comps = r.connected_components(nodes, edges, min_weight=2)
        # a-b unidos (peso 3); c,d sueltos (peso 1 < 2)
        assert ["a", "b"] in comps
        assert ["c"] in comps and ["d"] in comps

    @pytest.mark.unit
    def test_entity_is_root_component(self):
        edges = [
            {"a": "0xroot", "b": "0xsib", "weight": 5},   # fuerte
            {"a": "0xsib", "b": "0xcousin", "weight": 4},  # fuerte
            {"a": "0xroot", "b": "0xstranger", "weight": 1},  # débil
        ]
        g = r.build_entity_graph("0xROOT", edges, min_weight=3)
        assert set(g["entity"]) == {"0xroot", "0xsib", "0xcousin"}
        assert "0xstranger" not in g["entity"]
        assert g["entity_size"] == 3
        root_node = next(n for n in g["nodes"] if n["is_root"])
        assert root_node["in_entity"] is True

    @pytest.mark.unit
    def test_isolated_root(self):
        g = r.build_entity_graph("0xalone", [], min_weight=2)
        assert g["entity"] == ["0xalone"] and g["entity_size"] == 1

    @pytest.mark.unit
    def test_deterministic(self):
        edges = [{"a": "b", "b": "c", "weight": 2}, {"a": "a", "b": "b", "weight": 2}]
        g1 = r.build_entity_graph("a", edges, min_weight=2)
        g2 = r.build_entity_graph("a", edges, min_weight=2)
        assert g1["entity"] == g2["entity"]
        assert [n["address"] for n in g1["nodes"]] == [n["address"] for n in g2["nodes"]]
