"""
get_smart_money.py — Caso de uso: radar de dinero inteligente.

Sobre el histórico propio de movimientos de ballenas, identifica las direcciones
cuyos depósitos/retiradas de exchanges ANTICIPARON el precio: retiró antes de
subir, depositó antes de caer. La dirección de interés es siempre el lado NO
exchange del movimiento (quien deposita o quien retira).

Honestidad: solo puntúan movimientos cuyo horizonte ya transcurrió y direcciones
con muestra mínima; los activos sin serie de precios (tokens sin par en Binance)
quedan fuera y se informa cuántos movimientos no pudieron evaluarse.
"""

import logging

logger = logging.getLogger(__name__)

_HORIZON_HOURS = 24
_LOOKBACK_DAYS_MAX = 90
_MIN_MOVES = 3


class GetSmartMoneyUseCase:
    """Ranking de direcciones por retorno capturado de sus movimientos."""

    def execute(self, chain: str = "ethereum", days: int = 30) -> dict:
        from datetime import datetime, timedelta, timezone as dt_tz

        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
        from core.domain.services.onchain_flow import FROM_EXCHANGE, TO_EXCHANGE
        from core.domain.services.smart_money import evaluate_movements, score_addresses
        from core.infrastructure.persistence.models import WhaleMovementSnapshot

        chain = (chain or "ethereum").strip().lower()
        days = min(max(int(days), 1), _LOOKBACK_DAYS_MAX)
        since = datetime.now(dt_tz.utc) - timedelta(days=days)

        snapshots = list(
            WhaleMovementSnapshot.objects
            .filter(chain=chain, moved_at__gte=since,
                    direction__in=[TO_EXCHANGE, FROM_EXCHANGE])
        )
        if not snapshots:
            return {
                "chain": chain, "window_days": days, "movements_total": 0,
                "movements_evaluated": 0, "leaderboard": [],
                "note": "Aún no hay histórico suficiente: el escáner acumula movimientos cada 15 min.",
            }

        # La dirección con intención es el lado NO exchange del movimiento.
        movements = []
        for s in snapshots:
            address = s.from_address if s.direction == TO_EXCHANGE else s.to_address
            if not address:
                continue
            movements.append({
                "address": address,
                "symbol": s.symbol,
                "direction": s.direction,
                "value_usd": s.value_usd,
                "ts_ms": int(s.moved_at.timestamp() * 1000),
            })

        # Series de precios horarias por activo implicado (los que no coticen
        # en la cadena Binance→CoinGecko quedan sin evaluar, y se dice).
        prices_by_symbol: dict[str, list[tuple[int, float]]] = {}
        for symbol in sorted({m["symbol"] for m in movements}):
            try:
                res = fetch_ohlcv_dataframe(symbol=symbol, interval="1h",
                                            limit=min(days * 24 + _HORIZON_HOURS, 1000))
                if res is not None and not res.df.empty:
                    df = res.df
                    prices_by_symbol[symbol] = list(zip(
                        df["timestamp"].astype("int64").tolist(),
                        df["close"].astype(float).tolist(),
                    ))
            except Exception as exc:  # noqa: BLE001 — un activo sin datos no rompe el radar
                logger.warning("smart_money: sin precios para %s: %s", symbol, exc)

        evaluated = evaluate_movements(movements, prices_by_symbol, horizon_hours=_HORIZON_HOURS)
        leaderboard = score_addresses(evaluated, min_moves=_MIN_MOVES)

        return {
            "chain": chain,
            "window_days": days,
            "horizon_hours": _HORIZON_HOURS,
            "min_moves": _MIN_MOVES,
            "movements_total": len(movements),
            "movements_evaluated": len(evaluated),
            "leaderboard": leaderboard,
            "note": "Acierto y retorno capturado ponderados por tamaño, evaluados contra el retorno "
                    f"de las {_HORIZON_HOURS}h posteriores a cada movimiento. Solo puntúan direcciones "
                    f"con ≥{_MIN_MOVES} movimientos resueltos. Rendimiento pasado ≠ garantía futura.",
        }
