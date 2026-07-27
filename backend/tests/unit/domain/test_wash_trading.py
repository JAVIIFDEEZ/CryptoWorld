"""
tests/unit/domain/test_wash_trading.py — Detección de wash trading (dominio puro).

Verifica que el round-trip (ida y vuelta entre las mismas direcciones) dispara
el score, que el flujo orgánico no, y las métricas y pares sospechosos.
"""

import pytest

from core.domain.services import wash_trading as w


def _t(frm, to, value, ts=1_700_000_000):
    return {"from": frm, "to": to, "value": value, "timestamp": ts}


class TestWashTrading:

    @pytest.mark.unit
    def test_pure_round_trip_is_flagged(self):
        # A↔B ida y vuelta el mismo valor, repetido → wash puro
        txs = []
        for i in range(8):
            txs.append(_t("0xa", "0xb", 100, 1_700_000_000 + i * 60))
            txs.append(_t("0xb", "0xa", 100, 1_700_000_000 + i * 60 + 30))
        out = w.detect_wash_trading(txs)
        assert out["available"] is True
        assert out["verdict"] == "MANIPULADO"
        assert out["round_trip_ratio"] == pytest.approx(1.0, abs=1e-6)
        assert out["suspicious_pairs"][0]["transfers"] == 16

    @pytest.mark.unit
    def test_organic_flow_is_clean(self):
        # Muchas direcciones distintas, sin reversos → orgánico
        txs = [_t(f"0xsrc{i}", f"0xdst{i}", 100 + i, 1_700_000_000 + i * 60)
               for i in range(20)]
        out = w.detect_wash_trading(txs)
        assert out["available"] is True
        assert out["verdict"] == "ORGÁNICO"
        assert out["round_trip_ratio"] == pytest.approx(0.0)
        assert out["suspicious_pairs"] == []

    @pytest.mark.unit
    def test_partial_round_trip_scales(self):
        # Mitad round-trip, mitad orgánico → score intermedio
        txs = []
        for i in range(6):
            txs.append(_t("0xa", "0xb", 100))
            txs.append(_t("0xb", "0xa", 100))
        for i in range(12):
            txs.append(_t(f"0xu{i}", f"0xv{i}", 100))
        out = w.detect_wash_trading(txs)
        assert 0.0 < out["round_trip_ratio"] < 1.0
        assert out["verdict"] in ("DUDOSO", "SOSPECHOSO", "MANIPULADO")

    @pytest.mark.unit
    def test_self_transfers_counted(self):
        txs = [_t("0xa", "0xa", 100) for _ in range(5)]
        txs += [_t(f"0xs{i}", f"0xd{i}", 50) for i in range(8)]
        out = w.detect_wash_trading(txs)
        assert out["self_transfers"] == 5

    @pytest.mark.unit
    def test_insufficient_data(self):
        out = w.detect_wash_trading([_t("0xa", "0xb", 1)], min_transfers=10)
        assert out["available"] is False

    @pytest.mark.unit
    def test_metrics_present(self):
        txs = [_t("0xa", "0xb", 100), _t("0xb", "0xa", 100)] * 6
        out = w.detect_wash_trading(txs)
        assert {"wash_score", "top5_pair_share_pct", "unique_addresses",
                "total_transfers"} <= set(out)
        assert out["unique_addresses"] == 2
