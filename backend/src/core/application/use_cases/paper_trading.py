"""
paper_trading.py — Cartera virtual que sigue una estrategia generada en vivo.

Cierra el bucle entre el generador y la operativa real: el backtest dice cómo se
habría comportado una estrategia en el pasado; el paper trading lo verifica hacia
delante, con datos en vivo y sin arriesgar dinero. Una cartera "activa" se
reevalúa periódicamente: si la señal causal de la estrategia (Módulo 0) cambia a
compra o venta, se abre o cierra la posición aplicando costes (comisión +
slippage) coherentes con el motor de backtest, y se registra el P&L realizado.

Diseño deliberadamente simple y honesto:
  · Una sola posición larga a la vez (todo dentro / todo fuera), igual que el
    backtest base con sizing "full" → el paper trading es comparable al backtest.
  · Coste por operación en puntos básicos sobre el nocional, idéntico al CostModel.
  · Marca a mercado en cada evaluación para exponer patrimonio y P&L latente.
"""

import logging

logger = logging.getLogger(__name__)

# Velas suficientes para calentar los indicadores más lentos del spec.
_SIGNAL_LIMIT = 200


def _apply_signal(account, signal: str, price: float) -> "object | None":
    """Aplica una señal a la cartera marcándola a mercado. Devuelve el PaperTrade
    creado (apertura o cierre) o None si no hubo operación.

    No persiste: el llamador guarda la cuenta y el trade en una transacción.
    """
    from core.infrastructure.persistence.models import PaperTrade

    account.last_price = float(price)
    cost_rate = (account.commission_bps + account.slippage_bps) / 10000.0
    trade = None

    flat = account.units <= 0
    if signal == "BUY" and flat and account.cash > 0:
        # Abrir: invertir todo el efectivo. El slippage encarece la entrada y la
        # comisión consume capital → se compran menos unidades de las "teóricas".
        fill = price * (1.0 + cost_rate)
        units = account.cash / fill
        cost = account.cash - units * price          # comisión + slippage en moneda
        account.units = units
        account.entry_price = fill                   # coste medio (ya incluye el coste)
        cash_before = account.cash
        account.cash = 0.0
        trade = PaperTrade(
            account=account, side="BUY", price=float(price), fill_price=float(fill),
            units=float(units), cost=float(cost), cash_after=0.0,
            equity_after=float(account.equity),
        )
        logger.debug("paper open #%s %.6f @ %.4f (de %.2f)", account.id, units, fill, cash_before)

    elif signal == "SELL" and not flat:
        # Cerrar: el slippage abarata la salida y la comisión reduce lo ingresado.
        fill = price * (1.0 - cost_rate)
        proceeds = account.units * fill
        gross = account.units * price
        cost = gross - proceeds
        invested = account.units * (account.entry_price or price)
        pnl = proceeds - invested
        pnl_pct = (fill / account.entry_price - 1.0) * 100.0 if account.entry_price else 0.0
        account.cash += proceeds
        units_closed = account.units
        account.units = 0.0
        account.entry_price = None
        account.realized_pnl += pnl
        account.trades_count += 1
        account.wins += int(pnl > 0)
        trade = PaperTrade(
            account=account, side="SELL", price=float(price), fill_price=float(fill),
            units=float(units_closed), cost=float(cost), cash_after=float(account.cash),
            equity_after=float(account.equity), pnl=float(pnl), pnl_pct=round(float(pnl_pct), 4),
        )
        logger.debug("paper close #%s pnl %.2f (%.2f%%)", account.id, pnl, pnl_pct)

    return trade


class EvaluatePaperTradingUseCase:
    """Reevalúa todas las carteras de paper trading activas sobre los datos más
    recientes y ejecuta sus señales. Pensada para Celery beat."""

    def execute(self) -> dict:
        from django.db import transaction
        from django.utils import timezone
        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
        from core.domain.services.strategy_spec import signal_state
        from core.infrastructure.persistence.models import PaperTradingAccount

        accounts = list(
            PaperTradingAccount.objects.select_related("strategy").filter(is_active=True)
        )
        evaluated = trades = 0
        ohlcv_cache: dict = {}

        for acc in accounts:
            key = (acc.asset_symbol, acc.interval)
            if key not in ohlcv_cache:
                res = fetch_ohlcv_dataframe(symbol=acc.asset_symbol, interval=acc.interval, limit=_SIGNAL_LIMIT)
                ohlcv_cache[key] = res.df if (res and not res.df.empty) else None
            df = ohlcv_cache[key]
            if df is None:
                continue

            evaluated += 1
            signal = signal_state(df, acc.strategy.spec)["signal"]
            price = float(df["close"].iloc[-1])
            with transaction.atomic():
                trade = _apply_signal(acc, signal, price)
                acc.last_signal = signal
                acc.last_eval_at = timezone.now()
                acc.save(update_fields=[
                    "cash", "units", "entry_price", "last_price", "realized_pnl",
                    "trades_count", "wins", "last_signal", "last_eval_at", "updated_at",
                ])
                if trade is not None:
                    trade.save()
                    trades += 1

        logger.info("paper_trading: %d carteras evaluadas, %d operaciones", evaluated, trades)
        return {"evaluated": evaluated, "trades": trades}


class PaperTradingListUseCase:
    """Resumen de las carteras de paper trading del usuario."""

    def execute(self, owner) -> dict:
        from core.infrastructure.persistence.models import PaperTradingAccount

        qs = (
            PaperTradingAccount.objects.select_related("strategy", "strategy__asset")
            .filter(owner=owner).order_by("-started_at")
        )
        return {"count": qs.count(), "results": [_serialize_account(a) for a in qs]}


class PaperTradingDetailUseCase:
    """Detalle de una cartera con su historial de operaciones."""

    def execute(self, owner, account_id: int, trades_limit: int = 50) -> dict | None:
        from core.infrastructure.persistence.models import PaperTradingAccount

        acc = (
            PaperTradingAccount.objects.select_related("strategy", "strategy__asset")
            .filter(id=account_id, owner=owner).first()
        )
        if acc is None:
            return None
        data = _serialize_account(acc)
        data["trades"] = [
            {
                "id": t.id,
                "side": t.side,
                "price": round(t.price, 6),
                "fill_price": round(t.fill_price, 6),
                "units": round(t.units, 8),
                "cost": round(t.cost, 4),
                "cash_after": round(t.cash_after, 2),
                "equity_after": round(t.equity_after, 2),
                "pnl": round(t.pnl, 4) if t.pnl is not None else None,
                "pnl_pct": t.pnl_pct,
                "created_at": t.created_at.isoformat(),
            }
            for t in acc.trades.all()[:trades_limit]
        ]
        return data


def _serialize_account(a) -> dict:
    win_rate = round(a.wins / a.trades_count, 4) if a.trades_count else None
    return {
        "id": a.id,
        "strategy_id": a.strategy_id,
        "strategy_name": a.strategy.name if a.strategy else None,
        "asset_symbol": a.asset_symbol,
        "interval": a.interval,
        "initial_capital": a.initial_capital,
        "cash": round(a.cash, 2),
        "units": round(a.units, 8),
        "entry_price": round(a.entry_price, 6) if a.entry_price else None,
        "last_price": round(a.last_price, 6) if a.last_price else None,
        "position_value": round(a.position_value, 2),
        "equity": round(a.equity, 2),
        "realized_pnl": round(a.realized_pnl, 2),
        "total_return_pct": round(a.total_return_pct, 4),
        "in_position": a.units > 0,
        "is_active": a.is_active,
        "trades_count": a.trades_count,
        "wins": a.wins,
        "win_rate": win_rate,
        "last_signal": a.last_signal,
        "last_eval_at": a.last_eval_at.isoformat() if a.last_eval_at else None,
        "started_at": a.started_at.isoformat(),
    }
