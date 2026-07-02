"""
tests/integration/test_onchain_pressure.py — Edge on-chain: flujo de exchanges.

Verifica la clasificación de movimientos por etiquetas (dominio), la agregación
de presión con veredicto honesto, el escáner persistente con deduplicación y el
endpoint del indicador.
"""

from datetime import datetime, timedelta, timezone as dt_tz

import pytest

from core.domain.services.onchain_flow import (
    aggregate_pressure, bucket_flows, classify_flow, is_exchange_label, pressure_verdict,
)
from core.application.use_cases.onchain_pressure import (
    DetectPressureSignalUseCase, OnChainPressureUseCase, ScanWhaleMovementsUseCase,
)


class TestClassification:

    @pytest.mark.unit
    def test_exchange_labels_detected(self):
        assert is_exchange_label("Binance 14")
        assert is_exchange_label("MEXC: Deposit Address")
        assert is_exchange_label("Coinbase 10")
        assert is_exchange_label("OKX Hot Wallet")
        assert not is_exchange_label("Vitalik Buterin")
        assert not is_exchange_label(None)
        assert not is_exchange_label("")

    @pytest.mark.unit
    def test_flow_directions(self):
        assert classify_flow(None, "Binance 14") == "to_exchange"
        assert classify_flow("Kraken 4", None) == "from_exchange"
        assert classify_flow("Binance 14", "Coinbase 10") == "between_exchanges"
        assert classify_flow("wallet-a", "wallet-b") == "unknown"


class TestAggregation:

    @pytest.mark.unit
    def test_pressure_score_and_verdict(self):
        movements = [
            {"direction": "from_exchange", "value_usd": 3_000_000},   # retirada
            {"direction": "from_exchange", "value_usd": 2_000_000},
            {"direction": "to_exchange", "value_usd": 1_000_000},     # depósito
            {"direction": "unknown", "value_usd": 9_000_000},         # no puntúa
            {"direction": "between_exchanges", "value_usd": 500_000}, # no puntúa
        ] + [{"direction": "to_exchange", "value_usd": 1} for _ in range(3)]
        s = aggregate_pressure(movements)
        assert s.outflow_usd == pytest.approx(5_000_000)
        assert s.inflow_usd == pytest.approx(1_000_003)
        # (5M − 1M) / 6M ≈ +0.67 → acumulación
        assert s.pressure > 0.25
        verdict, _ = pressure_verdict(s)
        assert verdict == "ACUMULACION"

    @pytest.mark.unit
    def test_selling_pressure(self):
        movements = [{"direction": "to_exchange", "value_usd": 5_000_000} for _ in range(5)]
        s = aggregate_pressure(movements)
        assert s.pressure == -1.0
        assert pressure_verdict(s)[0] == "PRESION_VENDEDORA"

    @pytest.mark.unit
    def test_small_sample_is_honest(self):
        s = aggregate_pressure([{"direction": "to_exchange", "value_usd": 1_000_000}])
        assert pressure_verdict(s)[0] == "INSUFICIENTE"

    @pytest.mark.unit
    def test_buckets_group_by_time(self):
        base = 1_700_000_000_000
        movements = [
            {"direction": "to_exchange", "value_usd": 100, "ts_ms": base},
            {"direction": "from_exchange", "value_usd": 300, "ts_ms": base + 7 * 3600 * 1000},
        ]
        series = bucket_flows(movements, bucket_hours=6)
        assert len(series) == 2
        assert series[0]["inflow_usd"] == 100 and series[1]["outflow_usd"] == 300


class _FakeWhales:
    """GetWhaleMovements falso con movimientos etiquetados controlados."""

    def __init__(self):
        self.calls = 0

    def execute(self, chain, min_usd=100000, limit=100):
        self.calls += 1
        return {"movements": [
            {"kind": "native", "symbol": "ETH", "amount": 1000.0, "value_usd": 1_600_000.0,
             "from": {"address": "0xW1", "label": None},
             "to": {"address": "0xB1", "label": "Binance 14"},
             "hash": "0xaaa", "timestamp": "2026-07-01T10:00:00Z"},
            {"kind": "token", "symbol": "USDC", "amount": 2_000_000.0, "value_usd": 2_000_000.0,
             "from": {"address": "0xK1", "label": "Kraken 4"},
             "to": {"address": "0xW2", "label": None},
             "hash": "0xbbb", "timestamp": "2026-07-01T11:00:00Z"},
        ]}


class TestScanner:

    @pytest.mark.integration
    def test_scan_persists_classified_movements(self, db):
        from core.infrastructure.persistence.models import WhaleMovementSnapshot
        out = ScanWhaleMovementsUseCase(whales_uc=_FakeWhales()).execute(chains=("ethereum",))
        assert out["created"] == 2
        deposit = WhaleMovementSnapshot.objects.get(tx_hash="0xaaa")
        assert deposit.direction == "to_exchange" and deposit.to_label == "Binance 14"
        withdrawal = WhaleMovementSnapshot.objects.get(tx_hash="0xbbb")
        assert withdrawal.direction == "from_exchange"

    @pytest.mark.integration
    def test_rescan_deduplicates(self, db):
        from core.infrastructure.persistence.models import WhaleMovementSnapshot
        uc = ScanWhaleMovementsUseCase(whales_uc=_FakeWhales())
        uc.execute(chains=("ethereum",))
        out2 = uc.execute(chains=("ethereum",))   # segunda pasada: mismos movimientos
        assert out2["created"] == 0
        assert WhaleMovementSnapshot.objects.count() == 2


class TestPressureUseCase:

    def _snapshot(self, direction, value, hours_ago=1, tx="0x1", symbol="ETH"):
        from core.infrastructure.persistence.models import WhaleMovementSnapshot
        return WhaleMovementSnapshot.objects.create(
            chain="ethereum", symbol=symbol, kind="native", amount=1.0,
            value_usd=value, direction=direction, tx_hash=tx,
            from_address="0xa", to_address="0xb",
            moved_at=datetime.now(dt_tz.utc) - timedelta(hours=hours_ago),
        )

    @pytest.mark.integration
    def test_window_filters_and_aggregates(self, db):
        for i in range(6):
            self._snapshot("from_exchange", 1_000_000, hours_ago=2, tx=f"0xin{i}")
        self._snapshot("to_exchange", 500_000, hours_ago=3, tx="0xout")
        self._snapshot("to_exchange", 9_000_000, hours_ago=100, tx="0xold")  # fuera de ventana

        r = OnChainPressureUseCase().execute(chain="ethereum", hours=24)
        assert r["total_movements"] == 7          # el antiguo queda fuera
        assert r["outflow_usd"] == pytest.approx(6_000_000)
        assert r["inflow_usd"] == pytest.approx(500_000)
        assert r["verdict"] == "ACUMULACION"
        assert len(r["top_movements"]) == 7
        assert r["series"]                         # hay serie temporal

    @pytest.mark.integration
    def test_empty_history_is_honest(self, db):
        r = OnChainPressureUseCase().execute(chain="ethereum", hours=24)
        assert r["total_movements"] == 0
        assert r["verdict"] == "INSUFICIENTE"


class TestApi:

    @pytest.mark.integration
    def test_requires_auth(self, api_client):
        assert api_client.get("/api/blockchain/pressure/").status_code == 401

    @pytest.mark.integration
    def test_endpoint_returns_pressure(self, authenticated_client):
        resp = authenticated_client.get("/api/blockchain/pressure/", {"chain": "ethereum", "hours": 24})
        assert resp.status_code == 200
        assert set(resp.data) >= {"pressure", "inflow_usd", "outflow_usd", "verdict", "series"}


class TestPressureSignals:
    """Cambios de régimen del indicador → eventos para el centro de notificaciones."""

    def _snapshot(self, direction, value, tx, hours_ago=1):
        from core.infrastructure.persistence.models import WhaleMovementSnapshot
        WhaleMovementSnapshot.objects.create(
            chain="ethereum", symbol="ETH", kind="native", amount=1.0,
            value_usd=value, direction=direction, tx_hash=tx,
            from_address="0xa", to_address="0xb",
            moved_at=datetime.now(dt_tz.utc) - timedelta(hours=hours_ago),
        )

    def _accumulation(self):
        for i in range(6):
            self._snapshot("from_exchange", 1_000_000, f"0xacc{i}")

    @pytest.mark.integration
    def test_regime_change_creates_event_once(self, db):
        from core.infrastructure.persistence.models import OnChainSignalEvent
        self._accumulation()
        out1 = DetectPressureSignalUseCase().execute(chains=("ethereum",))
        assert out1["created"] == 1
        ev = OnChainSignalEvent.objects.get()
        assert ev.verdict == "ACUMULACION" and ev.previous_verdict == ""

        # Mismo régimen en la siguiente pasada → sin evento nuevo
        out2 = DetectPressureSignalUseCase().execute(chains=("ethereum",))
        assert out2["created"] == 0
        assert OnChainSignalEvent.objects.count() == 1

    @pytest.mark.integration
    def test_transition_records_previous_verdict(self, db):
        from core.infrastructure.persistence.models import OnChainSignalEvent
        self._accumulation()
        DetectPressureSignalUseCase().execute(chains=("ethereum",))
        # El régimen gira a presión vendedora (muchos depósitos grandes)
        for i in range(20):
            self._snapshot("to_exchange", 5_000_000, f"0xsell{i}")
        DetectPressureSignalUseCase().execute(chains=("ethereum",))
        latest = OnChainSignalEvent.objects.first()
        assert latest.verdict == "PRESION_VENDEDORA"
        assert latest.previous_verdict == "ACUMULACION"

    @pytest.mark.integration
    def test_insufficient_sample_never_signals(self, db):
        from core.infrastructure.persistence.models import OnChainSignalEvent
        self._snapshot("to_exchange", 1_000_000, "0xlone")   # 1 solo movimiento
        out = DetectPressureSignalUseCase().execute(chains=("ethereum",))
        assert out["created"] == 0
        assert OnChainSignalEvent.objects.count() == 0
