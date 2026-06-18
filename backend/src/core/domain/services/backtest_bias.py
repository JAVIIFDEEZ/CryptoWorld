"""
backtest_bias.py — Detectores de sesgo del backtest (estilo Freqtrade).

Dos comprobaciones de integridad del backtest:

  - detect_lookahead_bias: re-genera las señales sobre datos truncados en una
    muestra de velas y comprueba si una señal pasada cambia al disponer de
    velas futuras (fuga del futuro / lookahead).
  - detect_recursive_instability: re-calcula el indicador empezando con
    distintas longitudes de histórico y mide si los valores tempranos derivan
    (los indicadores recursivos —EMA, RSI de Wilder— "arrastran" el seed;
    una SMA no).

Reciben funciones (`signal_fn`, `indicator_fn`) para ser genéricos y
testeables con casos sintéticos con y sin fuga. Capa de dominio, sin framework.
"""

import numpy as np


def detect_lookahead_bias(df, signal_fn, sample_size: int = 40, warmup: int = 20, seed: int = 42) -> dict:
    """
    signal_fn(df) -> array de señales alineado a df. Para una muestra de velas i
    re-genera las señales con datos solo hasta i y compara con la señal del
    backtest completo en i. Si difieren, hay fuga del futuro.
    """
    full = np.asarray(signal_fn(df), dtype=float)
    n = len(df)
    candidates = list(range(warmup, n))
    if not candidates:
        return {"checked": 0, "leaks": 0, "leak_ratio": 0.0, "is_leaky": False,
                "note": "Histórico insuficiente para el test de lookahead."}

    rng = np.random.default_rng(seed)
    if len(candidates) > sample_size:
        sample = sorted(int(x) for x in rng.choice(candidates, size=sample_size, replace=False))
    else:
        sample = candidates

    checked = 0
    leaks = 0
    leaking_indices = []
    for i in sample:
        try:
            truncated = np.asarray(signal_fn(df.iloc[: i + 1]), dtype=float)
        except Exception:
            # Algunos indicadores (p. ej. ADX de la librería ta) fallan en
            # ventanas demasiado cortas; ese punto no es evaluable, se omite.
            continue
        if truncated.size <= i:
            continue
        checked += 1
        if truncated[i] != full[i]:
            leaks += 1
            leaking_indices.append(i)

    leak_ratio = leaks / checked if checked else 0.0
    return {
        "checked": checked,
        "leaks": leaks,
        "leak_ratio": round(float(leak_ratio), 4),
        "is_leaky": leaks > 0,
        "leaking_indices": leaking_indices[:10],
    }


def detect_recursive_instability(
    df,
    indicator_fn,
    offsets=(30, 60, 90),
    eval_window: int = 40,
    warmup: int = 30,
    threshold: float = 0.05,
) -> dict:
    """
    indicator_fn(df) -> array del indicador alineado a df. Compara los valores
    del indicador en las mismas velas de calendario cuando se calcula con todo
    el histórico frente a empezar `offset` velas más tarde. La deriva relativa
    máxima mide la inestabilidad recursiva (0 = estable, p.ej. SMA).
    """
    full = np.asarray(indicator_fn(df), dtype=float)
    n = len(df)
    by_offset = []
    max_drift = 0.0

    for off in offsets:
        if off + warmup + eval_window >= n:
            continue
        trunc = np.asarray(indicator_fn(df.iloc[off:]), dtype=float)
        # Mismo tramo de calendario: trunc[j] ≡ full[off + j]
        full_seg = full[off + warmup: off + warmup + eval_window]
        trunc_seg = trunc[warmup: warmup + eval_window]
        if trunc_seg.size != full_seg.size:
            continue
        mask = ~np.isnan(full_seg) & ~np.isnan(trunc_seg)
        if not mask.any():
            continue
        denom = np.where(np.abs(full_seg[mask]) > 1e-9, np.abs(full_seg[mask]), 1.0)
        drift = float(np.max(np.abs(trunc_seg[mask] - full_seg[mask]) / denom))
        by_offset.append({"offset": int(off), "max_rel_drift": round(drift, 6)})
        max_drift = max(max_drift, drift)

    return {
        "max_rel_drift": round(float(max_drift), 6),
        "by_offset": by_offset,
        "is_unstable": max_drift > threshold,
    }
