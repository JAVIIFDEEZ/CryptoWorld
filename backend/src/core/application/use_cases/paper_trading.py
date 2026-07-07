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

# Umbrales de decadencia (decay) de una estrategia en vivo. Cuando se cruzan, la
# cartera se marca como decaída y se dispara la reoptimización del activo.
_DECAY_MIN_TRADES = 5        # nº mínimo de operaciones cerradas para juzgar
_DECAY_MAX_DRAWDOWN = 20.0   # % de caída desde el pico que se considera degradación
_DECAY_MAX_LOSS = -10.0      # % de rentabilidad total por debajo del cual también decae


def _check_decay(account, now) -> bool:
    """Marca la cartera como decaída si su rendimiento en vivo se ha degradado.
    Devuelve True solo en la transición (sana → decaída), para disparar la
    reoptimización una única vez."""
    if account.decayed or account.trades_count < _DECAY_MIN_TRADES:
        return False
    degraded = (
        account.drawdown_pct >= _DECAY_MAX_DRAWDOWN
        or account.total_return_pct <= _DECAY_MAX_LOSS
    )
    if degraded:
        account.decayed = True
        account.decayed_at = now
        return True
    return False


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


def _pair_realized_events(records) -> list[dict]:
    """Recorre los registros ENVIADOS de una cuenta (ascendentes) emparejando
    compras acumuladas con cada venta (posición única) y devuelve los eventos
    realizados: [{"pnl": float, "created_at": datetime}] — uno por venta."""
    events = []
    pos_amount = pos_cost = 0.0
    for r in records:
        px = r.fill_price if r.fill_price else r.ref_price
        if r.side == "buy":
            pos_amount += r.amount
            pos_cost += r.amount * px
        elif r.side == "sell" and pos_amount > 0:
            events.append({"pnl": r.amount * px - pos_cost, "created_at": r.created_at})
            pos_amount = pos_cost = 0.0
    return events


def daily_live_realized_pnl(owner) -> float:
    """PnL realizado HOY (UTC) en ejecución real, sumando todas las promociones
    del usuario. Es la métrica del límite de pérdida diaria del OMS: las ventas
    de hoy se emparejan con el coste de sus compras (aunque fueran de días
    anteriores), que es como un libro de órdenes real mide su día."""
    from django.utils import timezone
    from core.infrastructure.persistence.models import LiveOrderRecord

    today = timezone.now().date()
    total = 0.0
    # order_by() vacío: sin él, el ordering por defecto del modelo entra en el
    # DISTINCT y devuelve el mismo account_id repetido (gotcha clásico de Django).
    account_ids = (LiveOrderRecord.objects.filter(account__owner=owner, status="sent")
                   .order_by().values_list("account_id", flat=True).distinct())
    for account_id in account_ids:
        records = list(LiveOrderRecord.objects
                       .filter(account_id=account_id, status="sent")
                       .order_by("created_at"))
        for ev in _pair_realized_events(records):
            if ev["created_at"].date() == today:
                total += ev["pnl"]
    return round(total, 2)


def _daily_loss_blocked(owner) -> "float | None":
    """Si el usuario tiene límite diario y ya lo ha alcanzado, devuelve la
    pérdida de hoy (para el mensaje); si no, None."""
    try:
        from core.infrastructure.persistence.models import LiveRiskPolicy
        policy = LiveRiskPolicy.objects.filter(owner_id=owner if isinstance(owner, int) else owner.id).first()
        if policy is None or not policy.daily_loss_limit_usd:
            return None
        pnl_today = daily_live_realized_pnl(owner)
        if pnl_today <= -abs(policy.daily_loss_limit_usd):
            return pnl_today
        return None
    except Exception:  # noqa: BLE001 — el control de riesgo nunca rompe el paper
        logger.exception("daily_loss check falló")
        return None


def _mirror_live(account, trade, price: float, broker_factory=None) -> None:
    """Espeja una operación de paper en el exchange REAL del usuario, con tope.

    Reglas de seguridad:
      · Solo si la promoción está activa, con conexión viva del MISMO dueño.
      · El nocional de compra se CAPA a live_cap_usd por operación.
      · La venta liquida exactamente lo comprado en real (live_base_position),
        nunca más.
      · Cualquier error del broker DESACTIVA la ejecución real (kill-switch) y
        guarda el motivo: un fallo no puede repetirse en bucle cada 15 min.
    """
    from django.utils import timezone
    from core.interfaces.ws.broadcast import broadcast_notification

    if trade is None or not account.live_enabled:
        return
    connection = account.live_connection
    if connection is None or not connection.is_active or connection.owner_id != account.owner_id:
        account.live_enabled = False
        account.live_error = "Conexión de exchange no disponible: promoción desactivada."
        account.live_disabled_at = timezone.now()
        broadcast_notification(account.owner_id, {"kind": "live"})
        return

    from core.application.use_cases.broker_trading import _broker_for
    from core.infrastructure.external_apis.ccxt_broker import BrokerError
    from core.infrastructure.persistence.models import LiveOrderRecord

    factory = broker_factory or _broker_for
    symbol = f"{account.asset_symbol.upper()}/USDT"

    # Determinar la orden a espejar (lado y cantidad) antes de tocar el broker.
    if trade.side == "BUY":
        notional = min(float(account.live_cap_usd), float(account.cash) + trade.units * price)
        base_amount = round(notional / price, 8) if price > 0 else 0.0
        side = "buy"
    elif trade.side == "SELL" and account.live_base_position > 0:
        base_amount = round(account.live_base_position, 8)
        side = "sell"
    else:
        return
    if base_amount <= 0:
        return

    record = LiveOrderRecord(
        account=account, connection=connection, symbol=symbol, side=side,
        amount=base_amount, ref_price=float(price),
        notional_usd=round(base_amount * float(price), 2),
        is_testnet=connection.is_testnet,
    )

    # OMS: límite de pérdida diaria GLOBAL del usuario. Bloquea nuevas COMPRAS
    # (abrir riesgo) sin desactivar la promoción — mañana se reanuda sola. Las
    # ventas jamás se bloquean: reducir exposición siempre está permitido.
    if side == "buy":
        loss_today = _daily_loss_blocked(account.owner)
        if loss_today is not None:
            record.status = "blocked"
            record.error = (f"Límite de pérdida diaria alcanzado "
                            f"({loss_today:+.2f} USD hoy): compra no enviada.")[:300]
            record.save()
            broadcast_notification(account.owner_id, {"kind": "live"})
            logger.warning("OMS: compra bloqueada por límite diario (cuenta #%s)", account.id)
            return
    try:
        order = factory(connection).create_order(symbol, side, "market", base_amount)
        if side == "buy":
            account.live_base_position += base_amount
        else:
            account.live_base_position = 0.0
        record.status = "sent"
        record.broker_order_id = str(order.get("id") or "")[:80]
        fill = order.get("average") or order.get("price")
        record.fill_price = float(fill) if fill else None
        logger.info("paper→real #%s %s %s (%s)", account.id, side, symbol,
                    "testnet" if connection.is_testnet else "REAL")
    except BrokerError as exc:
        account.live_enabled = False
        account.live_error = f"Ejecución real desactivada: {exc}"
        account.live_disabled_at = timezone.now()
        record.status = "failed"
        record.error = str(exc)[:300]
        broadcast_notification(account.owner_id, {"kind": "live"})
        logger.error("paper→real kill-switch #%s: %s", account.id, exc)
    finally:
        record.save()


class EvaluatePaperTradingUseCase:
    """Reevalúa todas las carteras de paper trading activas sobre los datos más
    recientes y ejecuta sus señales. Pensada para Celery beat."""

    def __init__(self, broker_factory=None) -> None:
        self._broker_factory = broker_factory

    def execute(self) -> dict:
        from django.db import transaction
        from django.utils import timezone
        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
        from core.domain.services.strategy_spec import signal_state
        from core.infrastructure.persistence.models import (
            PaperEquitySnapshot, PaperTradingAccount,
        )

        accounts = list(
            PaperTradingAccount.objects
            .select_related("strategy", "live_connection")
            .filter(is_active=True)
        )
        evaluated = trades = 0
        decayed_pairs: set = set()
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
            now = timezone.now()
            signal = signal_state(df, acc.strategy.spec)["signal"]
            price = float(df["close"].iloc[-1])
            with transaction.atomic():
                trade = _apply_signal(acc, signal, price)
                # Promoción a real: espejar la operación con tope y kill-switch.
                _mirror_live(acc, trade, price, broker_factory=self._broker_factory)
                acc.last_signal = signal
                acc.last_eval_at = now
                # Mark-to-market: actualizar pico y detectar decadencia (decay).
                acc.peak_equity = max(acc.peak_equity, acc.initial_capital, acc.equity)
                just_decayed = _check_decay(acc, now)
                fields = [
                    "cash", "units", "entry_price", "last_price", "realized_pnl",
                    "trades_count", "wins", "last_signal", "last_eval_at",
                    "peak_equity", "decayed", "decayed_at", "updated_at",
                    "live_enabled", "live_base_position", "live_error", "live_disabled_at",
                ]
                acc.save(update_fields=fields)
                PaperEquitySnapshot.objects.create(
                    account=acc, equity=round(acc.equity, 2), price=price, in_position=acc.units > 0,
                )
                if trade is not None:
                    trade.save()
                    trades += 1
                if just_decayed:
                    decayed_pairs.add((acc.asset_symbol, acc.interval))

        logger.info("paper_trading: %d carteras evaluadas, %d operaciones, %d decaídas",
                    evaluated, trades, len(decayed_pairs))
        return {"evaluated": evaluated, "trades": trades, "decayed_pairs": sorted(decayed_pairs)}


class LiveOrdersUseCase:
    """Auditoría de las órdenes reales de una cartera + P&L real estimado.

    Como la promoción opera una única posición (compra(s) hasta el tope y venta
    que liquida todo), el P&L realizado se estima emparejando cada venta con el
    coste acumulado de las compras previas, usando el precio de ejecución del
    broker cuando existe y el de referencia si no (y diciéndolo)."""

    def execute(self, owner, account_id: int, limit: int = 50) -> dict | None:
        from core.infrastructure.persistence.models import PaperTradingAccount

        acc = PaperTradingAccount.objects.filter(id=account_id, owner=owner).first()
        if acc is None:
            return None

        records = list(acc.live_orders.order_by("created_at"))
        sent = [r for r in records if r.status == "sent"]
        failed = [r for r in records if r.status == "failed"]

        # P&L realizado estimado (posición única, la venta liquida todo).
        realized = 0.0
        est_used = False           # True si algún precio fue el de referencia
        pos_amount = pos_cost = 0.0
        for r in sent:
            px = r.fill_price if r.fill_price else r.ref_price
            if not r.fill_price:
                est_used = True
            if r.side == "buy":
                pos_amount += r.amount
                pos_cost += r.amount * px
            elif r.side == "sell" and pos_amount > 0:
                realized += r.amount * px - pos_cost
                pos_amount = pos_cost = 0.0

        def _slippage_bps(r) -> "float | None":
            """Deslizamiento REAL medido: ejecución vs referencia, firmado de
            forma que positivo = peor que la referencia (coste), en ambos lados."""
            if not r.fill_price or not r.ref_price:
                return None
            raw = (r.fill_price - r.ref_price) / r.ref_price * 10_000.0
            return round(raw if r.side == "buy" else -raw, 2)

        items = [
            {
                "id": r.id,
                "side": r.side,
                "symbol": r.symbol,
                "amount": round(r.amount, 8),
                "ref_price": round(r.ref_price, 6),
                "fill_price": round(r.fill_price, 6) if r.fill_price else None,
                "slippage_bps": _slippage_bps(r),
                "notional_usd": r.notional_usd,
                "is_testnet": r.is_testnet,
                "status": r.status,
                "error": r.error or None,
                "broker_order_id": r.broker_order_id or None,
                "created_at": r.created_at.isoformat(),
            }
            for r in list(reversed(records))[:limit]
        ]
        # Slippage real agregado vs el modelado en el backtest: si el real
        # supera de forma sostenida al modelo, los backtests son optimistas.
        measured = [s for s in (_slippage_bps(r) for r in sent) if s is not None]
        slippage = {
            "n_filled": len(measured),
            "avg_slippage_bps": round(sum(measured) / len(measured), 2) if measured else None,
            "modeled_slippage_bps": 5.0,
        }
        return {
            "account_id": acc.id,
            "orders": items,
            "orders_sent": len(sent),
            "orders_failed": len(failed),
            "slippage": slippage,
            "blocked_orders": sum(1 for r in records if r.status == "blocked"),
            "live_realized_pnl_usd": round(realized, 2),
            "pnl_is_estimate": est_used,
            "paper_realized_pnl_usd": round(acc.realized_pnl, 2),
            "note": "P&L real estimado emparejando ventas con el coste de las compras previas; "
                    "usa el precio de ejecución del broker cuando lo devuelve.",
        }


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
        data["equity_curve"] = _equity_curve(acc, max_points=300)
        return data


def _equity_curve(account, max_points: int = 300) -> list[dict]:
    """Curva de equity (patrimonio en el tiempo), submuestreada a max_points para
    no devolver miles de puntos a la gráfica."""
    qs = account.equity_snapshots.order_by("created_at")
    total = qs.count()
    if total == 0:
        return []
    step = max(1, total // max_points)
    points = list(qs.values("equity", "price", "created_at"))[::step]
    return [
        {"t": p["created_at"].isoformat(), "equity": round(p["equity"], 2), "price": round(p["price"], 6)}
        for p in points
    ]


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
        "drawdown_pct": round(a.drawdown_pct, 4),
        "in_position": a.units > 0,
        "is_active": a.is_active,
        "decayed": a.decayed,
        "decayed_at": a.decayed_at.isoformat() if a.decayed_at else None,
        "live_enabled": a.live_enabled,
        "live_connection_id": a.live_connection_id,
        "live_is_testnet": a.live_connection.is_testnet if a.live_connection else None,
        "live_cap_usd": a.live_cap_usd,
        "live_base_position": round(a.live_base_position, 8),
        "live_error": a.live_error or None,
        "live_disabled_at": a.live_disabled_at.isoformat() if a.live_disabled_at else None,
        "live_reconciled_at": a.live_reconciled_at.isoformat() if a.live_reconciled_at else None,
        "live_discrepancy": round(a.live_discrepancy, 8) if a.live_discrepancy is not None else None,
        "trades_count": a.trades_count,
        "wins": a.wins,
        "win_rate": win_rate,
        "last_signal": a.last_signal,
        "last_eval_at": a.last_eval_at.isoformat() if a.last_eval_at else None,
        "started_at": a.started_at.isoformat(),
    }


class ReconcileLivePositionsUseCase:
    """OMS: reconciliación periódica posición esperada ↔ balance real.

    Para cada promoción activa consulta el balance de la moneda base en el
    exchange y lo compara con live_base_position. Una discrepancia mayor que
    la tolerancia (restos de redondeo del exchange aparte) significa que el
    estado interno y la realidad han divergido — órdenes manuales del usuario,
    fills parciales, comisiones en especie — y eso se registra y se notifica,
    porque operar sobre un estado falso es como los sistemas reales pierden
    dinero. Pensada para Celery beat."""

    # Tolerancia: 1% de la posición o polvo absoluto, lo que sea mayor.
    _REL_TOL = 0.01
    _ABS_TOL = 1e-6

    def __init__(self, broker_factory=None) -> None:
        self._broker_factory = broker_factory

    def execute(self) -> dict:
        from django.utils import timezone
        from core.application.use_cases.broker_trading import _broker_for
        from core.infrastructure.persistence.models import PaperTradingAccount
        from core.interfaces.ws.broadcast import broadcast_notification

        factory = self._broker_factory or _broker_for
        accounts = list(
            PaperTradingAccount.objects.select_related("live_connection")
            .filter(is_active=True, live_enabled=True, live_connection__isnull=False)
        )
        checked = mismatches = 0
        for acc in accounts:
            try:
                balances = factory(acc.live_connection).fetch_balance()
                base = acc.asset_symbol.upper()
                actual = 0.0
                for b in balances if isinstance(balances, list) else []:
                    if (b.get("asset") or "").upper() == base:
                        actual = float(b.get("free") or 0.0) + float(b.get("used") or 0.0)
                        break
                expected = float(acc.live_base_position)
                diff = actual - expected
                tolerance = max(self._ABS_TOL, abs(expected) * self._REL_TOL)
                acc.live_reconciled_at = timezone.now()
                acc.live_discrepancy = round(diff, 8) if abs(diff) > tolerance else 0.0
                acc.save(update_fields=["live_reconciled_at", "live_discrepancy", "updated_at"])
                checked += 1
                if abs(diff) > tolerance:
                    mismatches += 1
                    broadcast_notification(acc.owner_id, {"kind": "live"})
                    logger.warning(
                        "OMS reconciliación #%s: esperado %.8f, real %.8f (Δ %.8f)",
                        acc.id, expected, actual, diff,
                    )
            except Exception as exc:  # noqa: BLE001 — una cuenta caída no frena el resto
                logger.warning("OMS reconciliación #%s falló: %s", acc.id, exc)
        logger.info("reconcile_live: %d cuentas, %d discrepancias", checked, mismatches)
        return {"checked": checked, "mismatches": mismatches}
