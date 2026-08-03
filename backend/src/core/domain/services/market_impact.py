"""
market_impact.py — Impacto de mercado y capacidad de una estrategia.

La pregunta que ningún backtest retail responde
───────────────────────────────────────────────
Todo backtest supone que las órdenes se ejecutan al precio observado. Eso es
cierto mientras la orden sea pequeña frente al volumen del mercado, y deja de
serlo exactamente cuando la estrategia empieza a gestionar dinero de verdad. Una
estrategia con Sharpe 3 sobre 10 000 € puede tener Sharpe 0 sobre 10 millones,
sin que nada haya cambiado salvo el tamaño.

La **capacidad** —el patrimonio máximo antes de que el impacto se coma el
edge— es por tanto una propiedad tan real de la estrategia como su Sharpe, y la
dimensión que separa un backtest retail de uno institucional.

El modelo de raíz cuadrada
──────────────────────────
El consenso empírico (Almgren, Kyle, Torre) es que el impacto crece con la
**raíz cuadrada** de la participación, no linealmente:

    impacto (bps) = γ · σ · √(Q / ADV)

donde Q es el tamaño de la orden, ADV el volumen medio diario y σ la volatilidad
diaria. La raíz importa: implica que doblar el tamaño no dobla el coste, pero
también que el coste **nunca deja de crecer** — no hay un tamaño «gratis» a
partir del cual la ejecución sea neutra.

`gamma` es el único parámetro libre, y su valor típico ronda 0.5-1.0 en mercados
líquidos. Se deja explícito y configurable en lugar de calibrarlo: calibrarlo
sobre el mismo histórico con el que se valida la estrategia sería añadir un
grado de libertad más al problema que todo este motor intenta contener.

Capa de dominio: NumPy puro.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class ImpactModel:
    """Parámetros del impacto de mercado."""
    gamma: float = 0.8           # coeficiente del modelo de raíz cuadrada
    # Participación máxima admisible sobre el volumen diario. Por encima, la
    # orden deja de ser ejecutable en un día sin mover el mercado de forma
    # evidente; 10 % es el límite prudente habitual en mesas institucionales.
    max_participation: float = 0.10


def impact_bps(notional: float, adv: float, daily_volatility: float,
               model: ImpactModel | None = None) -> float:
    """Impacto esperado de una orden, en puntos básicos sobre su precio."""
    m = model or ImpactModel()
    if notional <= 0 or adv <= 0 or daily_volatility <= 0:
        return 0.0
    participation = notional / adv
    return float(m.gamma * daily_volatility * np.sqrt(participation) * 10_000.0)


def estimate_capacity(bar_returns, trades: list, adv_usd: float,
                      daily_volatility: float, initial_capital: float = 10_000.0,
                      model: ImpactModel | None = None,
                      levels: tuple = (1e4, 1e5, 1e6, 1e7, 1e8)) -> dict:
    """
    Curva de rendimiento frente al patrimonio gestionado, y capacidad resultante.

    Para cada nivel de AUM se estima el impacto de las órdenes que la estrategia
    habría cursado y se resta del retorno. La **capacidad** es el mayor AUM en el
    que el Sharpe neto sigue por encima de la mitad del original: pasado ese
    punto, lo que queda del edge no compensa el riesgo de gestionarlo.

    Se necesita el ADV del activo y su volatilidad diaria; sin ellos no hay
    estimación posible y se dice, en lugar de devolver una capacidad inventada.
    """
    m = model or ImpactModel()
    r = np.asarray(bar_returns, dtype=float)
    if r.size < 2 or not trades:
        return {"capacity_usd": None, "note": "Sin operaciones para estimar capacidad."}
    if adv_usd <= 0 or daily_volatility <= 0:
        return {"capacity_usd": None,
                "note": "Sin volumen medio diario o volatilidad del activo no se "
                        "puede estimar el impacto: la capacidad queda indeterminada."}

    sd = float(r.std(ddof=1))
    base_sharpe = float(r.mean() / sd) if sd > 0 else 0.0
    n_trades = len(trades)
    # Rotación: cuántas veces se mueve el capital completo a lo largo del test.
    # Cada round-trip son dos órdenes (entrada y salida).
    turnover_orders = n_trades * 2

    curve: list[dict] = []
    capacity: float | None = None
    for aum in levels:
        # Nocional típico por orden a este nivel de patrimonio.
        order_notional = aum
        participation = order_notional / adv_usd
        cost_bps = impact_bps(order_notional, adv_usd, daily_volatility, m)
        # Coste total repartido sobre la serie: cada orden paga su impacto.
        total_cost = cost_bps / 10_000.0 * turnover_orders
        net = r - (total_cost / r.size)

        sd_net = float(net.std(ddof=1))
        net_sharpe = float(net.mean() / sd_net) if sd_net > 0 else 0.0
        feasible = participation <= m.max_participation

        curve.append({
            "aum_usd": float(aum),
            "participation_pct": round(participation * 100, 3),
            "impact_bps_per_order": round(cost_bps, 2),
            "net_sharpe": round(net_sharpe, 4),
            "sharpe_retained_pct": round(
                net_sharpe / base_sharpe * 100, 1) if abs(base_sharpe) > 1e-9 else 0.0,
            "feasible": feasible,
        })
        # Capacidad: último nivel que conserva la mitad del Sharpe Y es ejecutable.
        if feasible and base_sharpe > 0 and net_sharpe >= base_sharpe * 0.5:
            capacity = float(aum)

    return {
        "capacity_usd": capacity,
        "base_sharpe_per_period": round(base_sharpe, 4),
        "adv_usd": float(adv_usd),
        "daily_volatility": round(float(daily_volatility), 6),
        "gamma": m.gamma,
        "max_participation_pct": m.max_participation * 100,
        "n_orders": turnover_orders,
        "curve": curve,
        "note": (
            f"Capacidad estimada: {capacity:,.0f} USD — el patrimonio máximo que "
            "conserva al menos la mitad del Sharpe original con una participación "
            f"≤{m.max_participation * 100:.0f}% del volumen diario."
            if capacity else
            "La estrategia no conserva la mitad de su Sharpe ni en el nivel más "
            "bajo evaluado: su edge no sobrevive al coste de ejecutarlo."
        ),
    }


def average_daily_volume_usd(df, window: int = 30) -> float:
    """Volumen medio diario en USD de las últimas `window` velas."""
    if "volume" not in df or "close" not in df or len(df) == 0:
        return 0.0
    volume = df["volume"].to_numpy(dtype=float)[-window:]
    close = df["close"].to_numpy(dtype=float)[-window:]
    if volume.size == 0 or float(volume.sum()) <= 0:
        return 0.0
    return float(np.mean(volume * close))


def daily_volatility_of(df, window: int = 30) -> float:
    """Volatilidad diaria de los retornos de cierre en la ventana indicada."""
    if "close" not in df or len(df) < 3:
        return 0.0
    close = df["close"].to_numpy(dtype=float)
    returns = np.diff(close) / np.where(close[:-1] != 0, close[:-1], 1.0)
    sample = returns[-window:]
    return float(np.std(sample, ddof=1)) if sample.size >= 2 else 0.0
