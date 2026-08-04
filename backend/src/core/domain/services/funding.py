"""
funding.py — El coste de mantener abierto un perpetuo.

Un backtest de spot que ignora comisiones es optimista; uno de **perpetuos** que
ignora el funding es optimista de una forma peor, porque el error crece con el
tiempo que la posición permanece abierta. El funding se cobra cada 8 horas,
tenga o no razón la posición, y en cripto llega a costar decenas de puntos
básicos al día. Una estrategia de tendencia que aguanta semanas puede perder
todo su edge ahí sin que ninguna métrica del backtest lo insinúe.

Dos propiedades que obligan a guardar el histórico y no una media
─────────────────────────────────────────────────────────────────
· El funding es **fuertemente autocorrelacionado**: se agrupa en rachas largas
  del mismo signo. Aplicar su media anula justo lo que lo hace peligroso.
· Su signo se correlaciona con el sentimiento: es más caro estar largo
  precisamente cuando todo el mundo quiere estarlo. Promediar borra esa
  coincidencia, que es la que más daña a las estrategias de momento.

Convención de signo
───────────────────
`funding_rate` positivo = los largos pagan. Este motor es long-only, así que un
rate positivo es siempre un coste y uno negativo, un ingreso. Se respeta el
signo en lugar de tomar valor absoluto: cobrar cuando toca cobrar es parte de
medir bien.

Capa de dominio: NumPy puro, sin ORM.
"""

from __future__ import annotations

import numpy as np


def funding_per_bar(records, bar_open_times, interval_ms: int) -> np.ndarray:
    """
    Reparte las liquidaciones de funding sobre las velas que las contienen.

    `records` son pares (funding_time_ms, rate). Cada liquidación se imputa a la
    vela cuyo intervalo `[apertura, apertura+duración)` la contiene, y las varias
    que caigan en la misma vela se **suman**: en una vela diaria caben tres
    liquidaciones de 8 horas, y cobrar solo una subestimaría el coste en dos
    tercios.

    Las liquidaciones fuera del rango de velas se descartan en silencio: no hay
    posición que cobrar fuera del histórico simulado.
    """
    times = np.asarray(bar_open_times, dtype=np.int64)
    out = np.zeros(times.size, dtype=float)
    if times.size == 0 or interval_ms <= 0:
        return out

    for funding_time, rate in records:
        t = int(funding_time)
        # searchsorted da la primera vela que EMPIEZA después de t; la que lo
        # contiene es la anterior.
        idx = int(np.searchsorted(times, t, side="right")) - 1
        if idx < 0:
            continue
        if t >= int(times[idx]) + interval_ms:
            continue          # hueco en el histórico: la vela no cubre este pago
        out[idx] += float(rate)
    return out


def funding_from_dataframe(df, column: str = "funding_rate") -> np.ndarray | None:
    """Serie de funding por vela si el DataFrame la trae; None si no."""
    if column not in getattr(df, "columns", ()):
        return None
    arr = np.asarray(df[column], dtype=float)
    return np.where(np.isfinite(arr), arr, 0.0)


def annualized_cost_bps(rates, periods_per_year: float = 1095.0) -> float:
    """
    Coste medio de financiación anualizado, en puntos básicos.

    `periods_per_year` por defecto 1095 = 3 liquidaciones diarias × 365, que es
    la cadencia estándar de 8 horas. Es la cifra que hace comparable el funding
    con la comisión: ambos son sangrado, y el del funding suele ser mayor.
    """
    arr = np.asarray(list(rates), dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return 0.0
    return float(np.mean(arr) * periods_per_year * 10_000.0)


def describe(rates, periods_per_year: float = 1095.0) -> dict:
    """Resumen publicable del régimen de financiación de un tramo."""
    arr = np.asarray(list(rates), dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return {"n": 0, "note": "Sin histórico de financiación para este tramo."}

    positive = int(np.sum(arr > 0))
    annual_bps = annualized_cost_bps(arr, periods_per_year)
    return {
        "n": int(arr.size),
        "mean_bps": round(float(np.mean(arr)) * 10_000.0, 4),
        "max_bps": round(float(np.max(arr)) * 10_000.0, 4),
        "min_bps": round(float(np.min(arr)) * 10_000.0, 4),
        "pct_paid_by_longs": round(positive / arr.size * 100.0, 1),
        "annualized_cost_bps": round(annual_bps, 1),
        "note": (
            f"Los largos pagaron en el {positive / arr.size * 100:.0f}% de las "
            f"liquidaciones. Mantener la posición abierta todo el periodo habría "
            f"costado {annual_bps / 100:.2f}% anual solo en financiación"
            + (", un ingreso neto para el largo." if annual_bps < 0 else ".")
        ),
    }
