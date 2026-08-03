"""
backtest_execution.py — Núcleo de simulación realista del backtest.

Unifica la simulación de operaciones (antes duplicada en backtest_signals) y le
añade dos piezas que la convierten de juguete en herramienta realista:

  · Costes de transacción: comisión (bps por lado, sobre el nocional) y
    deslizamiento (bps sobre el precio de ejecución). Penalizan de forma natural
    el sobre-trading (estrategias que operan mucho pierden el edge en comisiones).
  · Gestión de riesgo intrabar: stop-loss, take-profit y trailing-stop evaluados
    contra el máximo/mínimo de cada vela (no solo el cierre), con la convención
    conservadora de que, si en la misma vela se tocan stop y objetivo, salta el
    stop primero.
  · Relleno desplazado: una señal de la vela `i` se ejecuta a la APERTURA de la
    vela `i+1`, nunca al cierre que la originó. Detalle en `simulate`.

Con `fill_next_bar=False`, costes nulos y sin gestión de riesgo el resultado es
idéntico al motor anterior (compatibilidad: la batería de tests lo verifica).

Capa de dominio: Python puro.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class CostModel:
    """Costes de ejecución por operación (cada lado)."""
    commission_bps: float = 0.0   # comisión sobre el nocional (10 bps = 0,1%)
    slippage_bps: float = 0.0     # deslizamiento del precio de ejecución

    @property
    def commission_rate(self) -> float:
        return self.commission_bps / 10_000.0

    @property
    def slippage_rate(self) -> float:
        return self.slippage_bps / 10_000.0


@dataclass(frozen=True)
class RiskModel:
    """Gestión de riesgo por operación (fracciones: 0.05 = 5%).

    max_bars: salida por tiempo — cierra la posición tras N velas (las
    estrategias de ruptura profesionales limitan la vida del trade).
    atr_stop_mult: stop a múltiplos del ATR medido EN LA BARRA DE ENTRADA —
    stop adaptado a la volatilidad del momento, no un % fijo."""
    stop_loss_pct: float | None = None
    take_profit_pct: float | None = None
    trailing_stop_pct: float | None = None
    max_bars: int | None = None
    atr_stop_mult: float | None = None

    @property
    def active(self) -> bool:
        return any(v is not None for v in (
            self.stop_loss_pct, self.take_profit_pct, self.trailing_stop_pct,
            self.max_bars, self.atr_stop_mult,
        ))


@dataclass(frozen=True)
class SizingModel:
    """
    Dimensionamiento de la posición al entrar.
      · "full":     invierte todo el capital disponible (comportamiento histórico).
      · "fraction": invierte una fracción fija del equity (0<fraction≤1).
      · "risk":     dimensiona para arriesgar `risk_pct` del equity si salta el
                    stop-loss (notional = risk_pct·equity / stop_loss_pct), con
                    apalancamiento máximo 1× (nunca más que el capital).
    """
    mode: str = "full"          # "full" | "fraction" | "risk"
    fraction: float = 1.0       # para "fraction"
    risk_pct: float = 0.02      # para "risk": fracción del equity arriesgada

    @property
    def active(self) -> bool:
        return self.mode != "full"


NO_COSTS = CostModel()
DEFAULT_SIZING = SizingModel()


def _position_notional(equity: float, sizing: SizingModel, risk: RiskModel | None) -> float:
    """Nocional a invertir en la entrada según el modelo de sizing (capado al equity)."""
    if sizing.mode == "fraction":
        notional = equity * sizing.fraction
    elif sizing.mode == "risk" and risk is not None and risk.stop_loss_pct:
        notional = sizing.risk_pct * equity / risk.stop_loss_pct
    else:  # "full"
        notional = equity
    return max(0.0, min(notional, equity))



def simulate(
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    signals: np.ndarray,
    initial_capital: float = 10_000.0,
    costs: CostModel | None = None,
    risk: RiskModel | None = None,
    sizing: SizingModel | None = None,
    atr: np.ndarray | None = None,
    open_: np.ndarray | None = None,
    fill_next_bar: bool = True,
) -> dict:
    """
    Simula la estrategia long-only sobre arrays de precio y señales. Con sizing
    "full" la posición ocupa todo el capital (todo dentro/todo fuera, idéntico al
    motor histórico); con "fraction"/"risk" mantiene parte en liquidez. Devuelve
    trades (con motivo de salida), curva de equity, retornos por vela y costes.

    Convención de ejecución (`fill_next_bar`, activa por defecto)
    ─────────────────────────────────────────────────────────────
    Una señal de la vela `i` se calcula con el cierre de esa vela, así que lo
    más pronto que se puede actuar sobre ella es la **apertura de la vela
    `i+1`**. Ejecutar al propio `close[i]` supondría observar el cierre y operar
    a ese mismo precio con latencia cero: es optimismo, y de un tipo que el
    detector de lookahead no captura porque las señales sí son causales — la
    fuga no está en la señal, está en el precio al que se rellena.

    El desplazamiento tiene una consecuencia deliberada: una señal en la última
    vela **no se ejecuta**, porque no existe la vela siguiente. Es correcto: no
    se puede operar sobre información que llega cuando los datos se acaban.

    Excepciones, y por qué lo son:
      · Los stops y objetivos se rellenan a su propio precio dentro de la vela
        que los toca. Son órdenes en reposo en el mercado, no decisiones que
        se toman al ver un cierre.
      · La salida por tiempo (`max_bars`) se rellena a la apertura de la vela
        en que vence: al abrirla ya se sabe que la posición ha agotado su vida,
        sin necesidad de ver su cierre.

    `fill_next_bar=False` restaura la convención histórica (relleno al cierre de
    la misma vela) y existe para los tests que comparan este motor con el
    anterior; no debería usarse para medir rendimiento.
    """
    costs = costs or NO_COSTS
    sizing = sizing or DEFAULT_SIZING
    cr, sr = costs.commission_rate, costs.slippage_rate
    use_risk = risk is not None and risk.active
    n = len(close)
    # Sin serie de aperturas, el desplazamiento usa el cierre de la vela
    # siguiente: sigue siendo honesto (no se opera al precio que originó la
    # señal), solo menos preciso que una apertura real.
    fill_price_series = open_ if open_ is not None else close

    capital = float(initial_capital)
    position = 0.0
    in_trade = False
    entry_price = 0.0
    entry_idx = 0
    entry_capital = 0.0
    high_water = 0.0
    entry_atr = None            # ATR en la barra de entrada (para atr_stop_mult)

    trades: list[dict] = []
    equity_curve = [float(initial_capital)]
    in_market_bars = 0
    total_commission = 0.0
    gross_traded = 0.0

    def do_buy(i: int, price: float) -> None:
        nonlocal capital, position, in_trade, entry_price, entry_idx, entry_capital, high_water
        nonlocal total_commission, gross_traded, entry_atr
        notional = _position_notional(capital, sizing, risk)   # equity == capital (flat)
        fee = notional * cr
        invested = notional - fee
        fill = price * (1.0 + sr)
        position = invested / fill if fill > 0 else 0.0
        entry_price = float(price)        # referencia de stops: precio de entrada
        entry_idx = i
        entry_capital = notional
        high_water = float(price)
        entry_atr = float(atr[i]) if atr is not None and np.isfinite(atr[i]) and atr[i] > 0 else None
        capital -= notional               # el resto queda en liquidez (sizing parcial)
        in_trade = True
        total_commission += fee
        gross_traded += notional

    def do_sell(i: int, exit_price: float, reason: str) -> None:
        nonlocal capital, position, in_trade, total_commission, gross_traded
        fill = exit_price * (1.0 - sr)
        gross = position * fill
        fee = gross * cr
        proceeds = gross - fee
        pnl_pct = (proceeds / entry_capital - 1.0) * 100.0 if entry_capital else 0.0
        trades.append({
            "entry_index": int(entry_idx),
            "exit_index": int(i),
            "entry_price": round(float(entry_price), 4),
            "exit_price": round(float(fill), 4),
            "pnl_pct": round(float(pnl_pct), 2),
            "result": "WIN" if pnl_pct > 0 else "LOSS",
            "exit_reason": reason,
        })
        capital += proceeds               # devuelve los ingresos a la liquidez
        position = 0.0
        in_trade = False
        total_commission += fee
        gross_traded += gross

    # Orden emitida por la señal de la vela anterior, a la espera de la apertura
    # de esta (0 = ninguna). Es el mecanismo del desplazamiento de ejecución.
    pending = 0

    for i in range(n):
        exited = False

        # ── 0) Ejecutar la orden pendiente a la APERTURA de esta vela ──
        # Va antes que todo lo demás porque la apertura es lo primero que
        # ocurre cronológicamente dentro de la vela.
        if pending != 0:
            fill_px = float(fill_price_series[i])
            if pending == 1 and not in_trade:
                do_buy(i, fill_px)
            elif pending == -1 and in_trade:
                do_sell(i, fill_px, "signal")
                exited = True
            pending = 0

        # ── 1) Gestión de riesgo intrabar (solo después de la barra de entrada) ──
        if in_trade and use_risk and i > entry_idx:
            hi, lo = float(high[i]), float(low[i])
            if risk.trailing_stop_pct is not None:
                high_water = max(high_water, hi)

            # Stop vinculante = el más alto entre stop fijo y trailing
            sl_price = entry_price * (1.0 - risk.stop_loss_pct) if risk.stop_loss_pct is not None else None
            trail_price = high_water * (1.0 - risk.trailing_stop_pct) if risk.trailing_stop_pct is not None else None
            # Stop por volatilidad: entry − mult·ATR(entrada), si el spec lo define.
            atr_price = (entry_price - risk.atr_stop_mult * entry_atr
                         if risk.atr_stop_mult is not None and entry_atr else None)
            stop_price, stop_reason = None, "stop_loss"
            for price, reason in ((sl_price, "stop_loss"), (trail_price, "trailing_stop"),
                                  (atr_price, "atr_stop")):
                if price is not None and (stop_price is None or price > stop_price):
                    stop_price, stop_reason = price, reason
            tp_price = entry_price * (1.0 + risk.take_profit_pct) if risk.take_profit_pct is not None else None

            # Convención conservadora: si en la misma vela se tocan stop y objetivo, salta el stop
            if stop_price is not None and lo <= stop_price:
                do_sell(i, stop_price, stop_reason)
                exited = True
            elif tp_price is not None and hi >= tp_price:
                do_sell(i, tp_price, "take_profit")
                exited = True

        # ── 1b) Salida por tiempo: la posición ha agotado su vida máxima ──
        # Se rellena a la APERTURA: al abrir la vela ya se sabe que la posición
        # ha cumplido su plazo, sin necesidad de ver cómo cierra.
        if not exited and in_trade and use_risk and risk.max_bars is not None and i - entry_idx >= risk.max_bars:
            time_exit_px = float(fill_price_series[i]) if fill_next_bar else float(close[i])
            do_sell(i, time_exit_px, "time_exit")
            exited = True

        # ── 2) Acciones por señal (si no se salió por riesgo en esta vela) ──
        # Con `fill_next_bar` la señal solo ENCOLA la orden: se rellenará a la
        # apertura de la vela siguiente, que es lo más pronto que se puede
        # actuar sobre un cierre recién observado.
        if not exited:
            if signals[i] == 1 and not in_trade:
                if fill_next_bar:
                    pending = 1
                else:
                    do_buy(i, float(close[i]))
            elif signals[i] == -1 and in_trade:
                if fill_next_bar:
                    pending = -1
                else:
                    do_sell(i, float(close[i]), "signal")

        # ── 3) Equity al cierre de la vela ──
        current_equity = capital + (position * float(close[i]) if in_trade else 0.0)
        equity_curve.append(float(current_equity))
        if in_trade:
            in_market_bars += 1

    # Cerrar posición abierta al último precio
    if in_trade:
        do_sell(n - 1, float(close[-1]), "end_of_data")

    return {
        "trades": trades,
        "equity_curve": equity_curve,
        "in_market_bars": in_market_bars,
        "final_capital": float(capital),
        "total_commission": float(total_commission),
        "total_commission_pct": round(total_commission / initial_capital * 100.0, 4) if initial_capital else 0.0,
        "turnover": round(gross_traded / initial_capital, 3) if initial_capital else 0.0,
    }
