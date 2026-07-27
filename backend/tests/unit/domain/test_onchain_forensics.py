"""
tests/unit/domain/test_onchain_forensics.py — Forense on-chain (dominio puro).

Verifica el rastreador de flujos (fan-out, peel chain, ciclo-seguro), la
concentración (Gini/HHI/veredicto) y la huella conductual (heatmap, arquetipos)
con datos sintéticos deterministas.
"""

import numpy as np
import pytest

from core.domain.services import onchain_forensics as f


def _tx(frm, to, value, ts=1_700_000_000):
    return {"from": frm, "to": to, "value": value, "timestamp": ts}


class TestFlowTree:

    @pytest.mark.unit
    def test_expands_top_counterparties_by_value(self):
        graph = {
            "0xroot": [_tx("0xroot", "0xa", 10), _tx("0xroot", "0xb", 5), _tx("0xroot", "0xc", 1)],
            "0xa": [_tx("0xa", "0xd", 8)],
        }
        out = f.build_flow_tree("0xROOT", lambda a: graph.get(a, []), depth=2, top_k=2)
        assert out["root"] == "0xroot"
        kids = out["tree"]["children"]
        assert [k["address"] for k in kids] == ["0xa", "0xb"]      # top-2 por valor
        assert kids[0]["share"] > kids[1]["share"]
        assert kids[0]["children"][0]["address"] == "0xd"          # expandió un nivel más

    @pytest.mark.unit
    def test_detects_fan_out(self):
        txs = [_tx("0xw", f"0x{i:040x}", 1.0) for i in range(1, 11)]   # 10 contrapartes
        out = f.build_flow_tree("0xw", lambda a: txs if a == "0xw" else [], depth=1)
        assert any(p["type"] == "fan_out" for p in out["patterns"])
        assert out["tree"]["fan_out"] == 10

    @pytest.mark.unit
    def test_detects_peel_chain(self):
        # Cadena: root →(90%) a →(90%) b →(90%) c
        graph = {
            "0xroot": [_tx("0xroot", "0xa", 90), _tx("0xroot", "0xz", 10)],
            "0xa": [_tx("0xa", "0xb", 90), _tx("0xa", "0xy", 10)],
            "0xb": [_tx("0xb", "0xc", 90), _tx("0xb", "0xx", 10)],
        }
        out = f.build_flow_tree("0xroot", lambda a: graph.get(a, []), depth=3, top_k=2)
        peel = [p for p in out["patterns"] if p["type"] == "peel_chain"]
        assert peel and peel[0]["depth"] >= 2

    @pytest.mark.unit
    def test_cycle_safe(self):
        graph = {"0xa": [_tx("0xa", "0xb", 5)], "0xb": [_tx("0xb", "0xa", 5)]}
        out = f.build_flow_tree("0xa", lambda a: graph.get(a, []), depth=4)
        # No hay recursión infinita; el nodo repetido se marca revisited
        b = out["tree"]["children"][0]
        assert b["address"] == "0xb"
        assert b["children"][0]["address"] == "0xa"
        assert b["children"][0]["revisited"] is True
        assert b["children"][0]["children"] == []

    @pytest.mark.unit
    def test_respects_node_budget(self):
        # Árbol amplio, pero max_nodes limita las expansiones (llamadas a fetch)
        calls = {"n": 0}
        def fetch(a):
            calls["n"] += 1
            return [_tx(a, f"0x{i}", 1.0) for i in range(3)]
        f.build_flow_tree("0xroot", fetch, depth=5, top_k=3, max_nodes=4)
        assert calls["n"] <= 4


class TestConcentration:

    @pytest.mark.unit
    def test_gini_extremes(self):
        assert f.gini_coefficient([5, 5, 5, 5]) == pytest.approx(0.0, abs=1e-9)
        assert f.gini_coefficient([0, 0, 0, 100]) > 0.7
        assert f.gini_coefficient([1]) is None

    @pytest.mark.unit
    def test_concentrated_token_flagged_critical(self):
        holders = [{"address": "0xwhale", "value": 900, "is_contract": False}]
        holders += [{"address": f"0x{i}", "value": 1, "is_contract": False} for i in range(100)]
        out = f.holder_concentration(holders)
        assert out["available"] is True
        assert out["verdict"] == "CRÍTICA"
        assert out["top10_share_pct"] > 60
        assert out["gini"] > 0.8
        assert out["top_holders"][0]["address"] == "0xwhale"

    @pytest.mark.unit
    def test_distributed_token(self):
        holders = [{"address": f"0x{i}", "value": 100 + (i % 5), "is_contract": False}
                   for i in range(200)]
        out = f.holder_concentration(holders)
        assert out["verdict"] == "DISTRIBUIDA"
        assert out["hhi"] < 0.05

    @pytest.mark.unit
    def test_insufficient_sample(self):
        assert f.holder_concentration([{"address": "0xa", "value": 1}])["available"] is False


class TestFingerprint:

    @pytest.mark.unit
    def test_heatmap_and_archetype_accumulator(self):
        # Muchas entradas de valor, pocas salidas, actividad esparcida → Acumuladora
        base = 1_700_000_000
        txs = [_tx("0xother", "0xme", 100, base + i * 86400 * 3) for i in range(6)]
        txs.append(_tx("0xme", "0xshop", 5, base + 86400 * 20))
        out = f.wallet_fingerprint("0xME", txs, now_ts=base + 86400 * 22)
        assert out["available"] is True
        assert out["in_count"] == 6 and out["out_count"] == 1
        assert out["archetype"] == "Acumuladora"
        assert len(out["heatmap"]) == 7 and len(out["heatmap"][0]) == 24
        assert sum(sum(r) for r in out["heatmap"]) == len(txs)

    @pytest.mark.unit
    def test_dormant_wallet(self):
        base = 1_600_000_000
        txs = [_tx("0xme", "0xa", 1, base + i * 3600) for i in range(5)]
        out = f.wallet_fingerprint("0xme", txs, now_ts=base + 86400 * 90)
        assert out["archetype"] == "Durmiente"
        assert out["days_since_last"] > 30

    @pytest.mark.unit
    def test_distributor_wallet(self):
        # 15 salidas a contrapartes distintas, esparcidas ~40 días con cadencia
        # irregular (no bot), 1 entrada → Distribuidora.
        base = 1_700_000_000
        offsets = [0, 130000, 400000, 900000, 1_200_000, 1_700_000, 2_100_000,
                   2_500_000, 2_900_000, 3_100_000, 3_050_000 + 90000, 3_400_000,
                   3_050_000 + 700000, 3_050_000 + 1_100_000, 3_050_000 + 400000]
        txs = [_tx("0xme", f"0x{i:040x}", 1, base + offsets[i]) for i in range(15)]
        txs.append(_tx("0xfund", "0xme", 100, base))
        out = f.wallet_fingerprint("0xme", txs, now_ts=base + 3_600_000 + 86400)
        assert out["archetype"] == "Distribuidora"
        assert out["unique_counterparties"] >= 10

    @pytest.mark.unit
    def test_heatmap_weekday_is_correct(self):
        # 2023-11-14 12:00 UTC fue MARTES → índice 1 (lunes=0)
        import datetime as dt
        ts = int(dt.datetime(2023, 11, 14, 12, 0, tzinfo=dt.timezone.utc).timestamp())
        txs = [_tx("0xme", "0xa", 1, ts), _tx("0xme", "0xb", 1, ts + 60), _tx("0xme", "0xc", 1, ts + 120)]
        out = f.wallet_fingerprint("0xme", txs, now_ts=ts + 3600)
        assert out["heatmap"][1][12] == 3

    @pytest.mark.unit
    def test_insufficient_activity(self):
        assert f.wallet_fingerprint("0xme", [_tx("0xme", "0xa", 1)], now_ts=1)["available"] is False
