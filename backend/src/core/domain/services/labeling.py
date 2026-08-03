"""
labeling.py — Etiquetado triple-barrera y meta-etiquetado (López de Prado).

Una regla de salida fija —«vende si el RSI sube de 70»— responde a la pregunta
equivocada. Lo que hay que saber de una entrada no es cuándo se cumple otra
condición técnica, sino **qué pasó primero**: ¿alcanzó el objetivo, saltó el
stop, o se agotó el tiempo sin que ocurriera ninguna de las dos?

Eso es el **triple-barrier method**:

    ┌─ barrera superior (objetivo)   +π·σ  → etiqueta +1
    │
  t₀├──────────────────────────────┐ barrera vertical (horizonte) → etiqueta 0
    │                              │
    └─ barrera inferior (stop)  −π·σ       → etiqueta −1

Las barreras se escalan con la **volatilidad estimada hasta t₀**, nunca con la
del futuro: un objetivo del 3 % significa cosas muy distintas en un mercado
tranquilo y en uno convulso, y usar la volatilidad realizada posterior sería
mirar el futuro.

Sobre el meta-etiquetado
────────────────────────
El modelo primario (aquí, la señal técnica) decide la **dirección**. El
meta-modelo no repite esa decisión: aprende **cuándo el primario acierta**, y su
probabilidad se convierte en el **tamaño** de la apuesta. Separar dirección de
tamaño es lo que permite apostar fuerte donde el sistema es fiable y casi nada
donde no lo es, sin cambiar la lógica de entrada.

Sobre los pesos por unicidad
────────────────────────────
Las etiquetas triple-barrera se solapan: una operación abierta cubre varias
velas, y varias etiquetas comparten los mismos retornos. Tratarlas como
independientes sobrepondera los tramos concurridos. El peso por *unicidad
media* corrige ese no-IID.

Capa de dominio: NumPy puro, sin framework ni ORM.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BarrierConfig:
    """Geometría de las tres barreras."""
    profit_mult: float = 2.0     # múltiplos de σ hasta el objetivo
    stop_mult: float = 1.0       # múltiplos de σ hasta el stop
    horizon: int = 10            # velas de la barrera vertical
    vol_window: int = 20         # ventana de la volatilidad (solo pasado)


def realized_volatility(close, window: int = 20) -> np.ndarray:
    """
    Volatilidad por vela estimada SOLO con datos hasta esa vela.

    El desplazamiento de una posición es lo que separa una estimación honesta de
    una fuga: sin él, la σ de la vela `i` incluiría el retorno de `i`, que es
    justo el que se quiere predecir.
    """
    c = np.asarray(close, dtype=float)
    if c.size < 2:
        return np.zeros(c.size)

    returns = np.zeros(c.size)
    returns[1:] = np.diff(c) / np.where(c[:-1] != 0, c[:-1], 1.0)

    vol = np.full(c.size, np.nan)
    for i in range(c.size):
        lo = max(0, i - window)
        sample = returns[lo:i]        # excluye i: solo pasado estricto
        if sample.size >= 2:
            vol[i] = float(np.std(sample, ddof=1))
    # Las primeras velas no tienen ventana: se rellenan con la primera σ válida
    # en lugar de inventarse un cero, que abriría barreras de anchura nula.
    valid = vol[np.isfinite(vol)]
    fill = float(valid[0]) if valid.size else 0.0
    return np.where(np.isfinite(vol), vol, fill)


def triple_barrier_labels(df, event_indices=None, config: BarrierConfig | None = None) -> dict:
    """
    Etiqueta cada evento con la barrera que toca primero.

    Devuelve, por evento: la etiqueta (+1 objetivo, −1 stop, 0 tiempo), la vela
    en que se resolvió, el retorno obtenido y las barreras usadas. `event_indices`
    permite etiquetar solo las velas donde hubo señal; por defecto, todas.

    El recorrido es intrabar y conservador: si en la misma vela se tocan las dos
    barreras, se da por buena la del stop. No se puede saber cuál llegó antes
    dentro de la vela, y suponer lo favorable es exactamente el sesgo que hace
    que un backtest prometa lo que la ejecución no da.
    """
    cfg = config or BarrierConfig()
    close = df["close"].to_numpy(dtype=float)
    high = df["high"].to_numpy(dtype=float) if "high" in df else close
    low = df["low"].to_numpy(dtype=float) if "low" in df else close
    n = close.size

    if n < cfg.vol_window + cfg.horizon + 2:
        return {"n_events": 0, "labels": [],
                "note": "Serie insuficiente para etiquetar con triple barrera."}

    vol = realized_volatility(close, cfg.vol_window)
    events = range(n) if event_indices is None else [int(i) for i in event_indices]

    labels: list[dict] = []
    for t0 in events:
        # Hace falta al menos una vela posterior para que exista resolución.
        if t0 < 0 or t0 >= n - 1:
            continue
        sigma = float(vol[t0])
        if sigma <= 0:
            continue

        entry = float(close[t0])
        upper = entry * (1.0 + cfg.profit_mult * sigma)
        lower = entry * (1.0 - cfg.stop_mult * sigma)
        vertical = min(t0 + cfg.horizon, n - 1)

        label, hit_idx, exit_price = 0, vertical, float(close[vertical])
        for i in range(t0 + 1, vertical + 1):
            touched_stop = low[i] <= lower
            touched_target = high[i] >= upper
            if touched_stop:                     # convención conservadora
                label, hit_idx, exit_price = -1, i, lower
                break
            if touched_target:
                label, hit_idx, exit_price = 1, i, upper
                break

        labels.append({
            "t0": int(t0),
            "t1": int(hit_idx),
            "label": int(label),
            "bars_held": int(hit_idx - t0),
            "entry_price": round(entry, 6),
            "exit_price": round(float(exit_price), 6),
            "ret": round(float(exit_price / entry - 1.0), 6),
            "sigma": round(sigma, 6),
            "upper": round(float(upper), 6),
            "lower": round(float(lower), 6),
        })

    counts = {"target": 0, "stop": 0, "timeout": 0}
    for lab in labels:
        counts["target" if lab["label"] == 1 else
               "stop" if lab["label"] == -1 else "timeout"] += 1

    return {
        "n_events": len(labels),
        "labels": labels,
        "counts": counts,
        "config": {
            "profit_mult": cfg.profit_mult, "stop_mult": cfg.stop_mult,
            "horizon": cfg.horizon, "vol_window": cfg.vol_window,
        },
        "note": (
            f"{len(labels)} eventos: {counts['target']} alcanzan objetivo, "
            f"{counts['stop']} saltan stop y {counts['timeout']} agotan el "
            "horizonte. Barreras escaladas por la volatilidad estimada hasta "
            "cada entrada, nunca con la posterior."
        ),
    }


def average_uniqueness(labels: list[dict], n_bars: int) -> np.ndarray:
    """
    Peso de cada etiqueta por su unicidad media (López de Prado, cap. 4).

    Dos operaciones que cubren las mismas velas comparten los mismos retornos:
    no son dos observaciones independientes. La unicidad media de una etiqueta
    es el inverso del número de etiquetas concurrentes en las velas que abarca;
    ponderar por ella antes de entrenar corrige que las muestras no sean IID y
    evita que los tramos más concurridos dominen el ajuste.
    """
    if not labels or n_bars <= 0:
        return np.array([], dtype=float)

    concurrency = np.zeros(n_bars, dtype=float)
    for lab in labels:
        concurrency[lab["t0"]:lab["t1"] + 1] += 1.0

    weights = np.zeros(len(labels), dtype=float)
    for k, lab in enumerate(labels):
        span = concurrency[lab["t0"]:lab["t1"] + 1]
        span = span[span > 0]
        weights[k] = float(np.mean(1.0 / span)) if span.size else 1.0
    return weights


def meta_label(labels: list[dict], primary_side: list[int] | None = None) -> dict:
    """
    Convierte las etiquetas triple-barrera en el objetivo del meta-modelo.

    El modelo primario ya decidió la dirección; el meta-modelo aprende **si esa
    decisión acierta**. La etiqueta binaria resultante es 1 cuando la operación
    del primario habría ganado y 0 cuando no — un problema mucho más fácil que
    predecir el mercado, y cuya probabilidad sirve directamente de tamaño.

    `primary_side` es el lado que propuso el primario (+1 largo, −1 corto). Si
    se omite, se asume largo: es lo que hace hoy el motor, que es long-only.
    """
    if not labels:
        return {"n": 0, "note": "Sin eventos que meta-etiquetar."}

    sides = ([1] * len(labels) if primary_side is None
             else [int(s) for s in primary_side])
    if len(sides) != len(labels):
        return {"n": 0, "note": "El lado del primario no cuadra con los eventos."}

    y: list[int] = []
    for lab, side in zip(labels, sides):
        # Acierta si el retorno, en la dirección propuesta, es positivo.
        y.append(1 if lab["ret"] * side > 0 else 0)

    hits = int(sum(y))
    return {
        "n": len(y),
        "y": y,
        "sample_weights": average_uniqueness(labels, max(lab["t1"] for lab in labels) + 1).tolist(),
        "hit_rate": round(hits / len(y) * 100.0, 1),
        "note": (
            f"El modelo primario acierta {hits} de {len(y)} entradas "
            f"({hits / len(y) * 100:.0f}%). El meta-modelo aprende a distinguir "
            "cuáles, y su probabilidad marca el tamaño de la apuesta."
        ),
    }


def bet_size(probability: float, max_fraction: float = 1.0, floor: float = 0.5) -> float:
    """
    Probabilidad de acierto → fracción de capital a arriesgar.

    Por debajo de `floor` el meta-modelo no aporta convicción y el tamaño es
    cero: no operar es una decisión, y la más rentable cuando no hay ventaja.
    Por encima, el tamaño escala linealmente con la confianza excedente y se
    acota en `max_fraction` — la fórmula de Kelly completa apuesta demasiado
    cuando la probabilidad está mal estimada, que es siempre.
    """
    p = float(np.clip(probability, 0.0, 1.0))
    if p <= floor or floor >= 1.0:
        return 0.0
    scaled = (p - floor) / (1.0 - floor)
    return float(np.clip(scaled, 0.0, 1.0) * max_fraction)
