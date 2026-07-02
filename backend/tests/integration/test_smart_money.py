"""
tests/integration/test_smart_money.py — Radar de dinero inteligente.

Verifica la evaluación de movimientos contra el retorno futuro (retirada acierta
si sube, depósito si baja; los horizontes no transcurridos no puntúan), la
puntuación por dirección ponderada por tamaño con muestra mínima, y el caso de
uso end-to-end sobre snapshots sembrados con precios mockeados.
"""

from datetime import datetime, timedelta, timezone as dt_tz

import numpy as np
import pandas as pd
import pytest

from core.domain.services.smart_money import evaluate_movements, price_at, score_addresses


def _prices(start_ms: int, closes: list[float], step_h: int = 1) -> list[tuple[int, float]]:
    return [(start_ms + i * step_h * 3600 * 1000, c) for i, c in enumerate(closes)]


class TestDomain:

    @pytest.mark.unit
    def test_price_at(self):
        prices = _prices(1_000_000, [100.0, 110.0, 120.0])
        assert price_at(prices, 1_000_000) == 100.0
        assert price_at(prices, 1_000_001) == 110.0            # siguiente vela
        assert price_at(prices, 99_999_999_999) is None        # fuera de serie

    @pytest.mark.unit
    def test_withdrawal_correct_when_price_rises(self):
        base = 1_700_000_000_000
        prices = {"ETH": _prices(base, [100.0] + [100.0 + i for i in range(1, 30)])}
        evaluated = evaluate_movements(
            [{"address": "0xW", "symbol": "ETH", "direction": "from_exchange",
              "value_usd": 1_000_000, "ts_ms": base}],
            prices, horizon_hours=24,
        )
        assert len(evaluated) == 1
        assert evaluated[0]["correct"] is True
        assert evaluated[0]["captured_pct"] > 0

    @pytest.mark.unit
    def test_deposit_correct_when_price_falls(self):
        base = 1_700_000_000_000
        prices = {"ETH": _prices(base, [100.0] + [100.0 - i for i in range(1, 30)])}
        evaluated = evaluate_movements(
            [{"address": "0xS", "symbol": "ETH", "direction": "to_exchange",
              "value_usd": 500_000, "ts_ms": base}],
            prices, horizon_hours=24,
        )
        assert evaluated[0]["correct"] is True                 # depositó y cayó
        assert evaluated[0]["forward_return_pct"] < 0
        assert evaluated[0]["captured_pct"] > 0                # con el signo de la intención

    @pytest.mark.unit
    def test_unresolved_horizon_excluded(self):
        base = 1_700_000_000_000
        prices = {"ETH": _prices(base, [100.0, 101.0, 102.0])}  # solo 3h de datos
        evaluated = evaluate_movements(
            [{"address": "0xW", "symbol": "ETH", "direction": "from_exchange",
              "value_usd": 1, "ts_ms": base}],
            prices, horizon_hours=24,                           # horizonte sin transcurrir
        )
        assert evaluated == []

    @pytest.mark.unit
    def test_scoring_needs_min_moves_and_weights_by_size(self):
        moves = (
            # 0xGOOD: 3 aciertos grandes
            [{"address": "0xGOOD", "value_usd": 1_000_000, "captured_pct": 5.0,
              "correct": True, "ts_ms": i} for i in range(3)]
            # 0xBAD: 2 fallos grandes + 1 acierto minúsculo → hit_rate ponderado ~0
            + [{"address": "0xBAD", "value_usd": 1_000_000, "captured_pct": -4.0,
                "correct": False, "ts_ms": i} for i in range(2)]
            + [{"address": "0xBAD", "value_usd": 10, "captured_pct": 1.0,
                "correct": True, "ts_ms": 9}]
            # 0xFEW: solo 2 movimientos → fuera por muestra mínima
            + [{"address": "0xFEW", "value_usd": 1_000_000, "captured_pct": 9.0,
                "correct": True, "ts_ms": i} for i in range(2)]
        )
        board = score_addresses(moves, min_moves=3)
        addrs = [r["address"] for r in board]
        assert addrs[0] == "0xGOOD" and "0xFEW" not in addrs
        good = board[0]
        assert good["hit_rate"] == 1.0 and good["avg_captured_pct"] == pytest.approx(5.0)
        bad = next(r for r in board if r["address"] == "0xBAD")
        assert bad["hit_rate"] < 0.01 and bad["avg_captured_pct"] < 0


class TestUseCase:

    @pytest.mark.integration
    def test_leaderboard_from_seeded_history(self, db, monkeypatch):
        from core.application.use_cases.get_smart_money import GetSmartMoneyUseCase
        from core.application.use_cases.ohlcv_fetcher import OhlcvFetchResult
        from core.infrastructure.persistence.models import WhaleMovementSnapshot

        now = datetime.now(dt_tz.utc)
        # 0xORACLE retiró 3 veces hace 5/4/3 días (y el precio subió después)
        for i, days_ago in enumerate([5, 4, 3]):
            WhaleMovementSnapshot.objects.create(
                chain="ethereum", symbol="ETH", kind="native", amount=100.0,
                value_usd=1_000_000, direction="from_exchange",
                from_address="0xKRAKEN", to_address="0xORACLE",
                tx_hash=f"0xsm{i}", moved_at=now - timedelta(days=days_ago),
            )

        # Serie horaria ascendente que cubre toda la ventana (10 días)
        n = 10 * 24
        start = int((now - timedelta(days=10)).timestamp() * 1000)
        closes = np.linspace(100.0, 200.0, n)
        df = pd.DataFrame({
            "timestamp": [start + i * 3_600_000 for i in range(n)],
            "open": closes, "high": closes + 1, "low": closes - 1, "close": closes,
            "volume": [1000.0] * n,
        })
        monkeypatch.setattr(
            "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
            lambda symbol, interval="1h", limit=1000, **kw: OhlcvFetchResult(df=df, source="binance"),
        )

        r = GetSmartMoneyUseCase().execute(chain="ethereum", days=30)
        assert r["movements_evaluated"] == 3
        assert len(r["leaderboard"]) == 1
        top = r["leaderboard"][0]
        assert top["address"] == "0xORACLE"
        assert top["hit_rate"] == 1.0 and top["avg_captured_pct"] > 0

    @pytest.mark.integration
    def test_empty_history_is_honest(self, db):
        from core.application.use_cases.get_smart_money import GetSmartMoneyUseCase
        r = GetSmartMoneyUseCase().execute(chain="ethereum")
        assert r["movements_total"] == 0 and r["leaderboard"] == []


class TestApi:

    @pytest.mark.integration
    def test_requires_auth(self, api_client):
        assert api_client.get("/api/blockchain/smartmoney/").status_code == 401

    @pytest.mark.integration
    def test_endpoint_returns_radar(self, authenticated_client):
        resp = authenticated_client.get("/api/blockchain/smartmoney/", {"chain": "ethereum"})
        assert resp.status_code == 200
        assert set(resp.data) >= {"leaderboard", "movements_total", "note"}
