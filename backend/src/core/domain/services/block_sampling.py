"""
block_sampling.py — Buscar sobre años de datos sin pagar años de cómputo.

El problema, medido
───────────────────
El coste del algoritmo genético es **lineal en velas**: 584 velas son ~4 min de
evolución exhaustiva, 4000 son ~20 min y 8000 son ~37. Usar tres años de velas
horarias (26 000) llevaría la búsqueda a más de dos horas, y sin tres años de
histórico lo que se encuentre estará ajustado a un único régimen de mercado.
Ambas cosas no pueden ser ciertas a la vez… salvo separando dos preguntas que
hasta ahora se respondían con el mismo cálculo.

La observación que lo desbloquea
────────────────────────────────
El fitness del GA solo tiene que **ORDENAR** genomas entre sí. No necesita ser
una estimación insesgada del rendimiento — de eso se encarga el gating, que sí
corre sobre el histórico completo. Y para ordenar bien basta con una muestra
representativa.

Por qué NO vale cualquier submuestra
────────────────────────────────────
· **Un tramo contiguo** haría que el GA optimizara para un solo régimen. Es
  exactamente el sesgo que se quiere evitar, solo que ahora deliberado.
· **Velas sueltas al azar** destruyen la serie temporal. Los indicadores tienen
  memoria y las operaciones duran varias velas: sobre velas inconexas ni unos ni
  otras significan nada.

La forma correcta es **muestreo por bloques**: varios tramos CONTIGUOS repartidos
por todo el histórico. Dentro de cada bloque la serie es real y los indicadores
funcionan; entre bloques hay saltos, y por eso **jamás se concatenan los
precios** —eso inventaría movimientos enormes en las costuras— sino los
RETORNOS de backtestear cada bloque por separado.

Tres reglas que sostienen la validez
────────────────────────────────────
1. **Calentamiento por bloque.** Cada bloque arrastra velas previas que sirven
   para cebar los indicadores y NO puntúan. Sin ellas, el arranque de cada
   bloque mediría el warm-up de una media de 200 velas en vez de la estrategia.
2. **La muestra es fija durante toda la ejecución.** Si cambiara entre genomas,
   se estarían comparando estrategias evaluadas sobre datos distintos y el
   ranking sería ruido con aspecto de selección.
3. **Cobertura verificable.** La muestra debe tocar todo el histórico, y eso se
   comprueba (`coverage_ratio`), no se supone.

Capa de dominio: NumPy puro.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Block:
    """Un tramo contiguo del histórico, con su calentamiento por delante."""
    warmup_start: int   # primera vela que se carga (no puntúa)
    score_start: int    # primera vela que cuenta para el resultado
    end: int            # exclusivo

    @property
    def scored_bars(self) -> int:
        return self.end - self.score_start

    @property
    def total_bars(self) -> int:
        return self.end - self.warmup_start


def plan_blocks(n_bars: int, n_blocks: int = 6, warmup: int = 200,
                target_scored: int | None = None) -> list[Block]:
    """
    Reparte `n_blocks` bloques uniformemente por todo el histórico.

    El reparto es **determinista y uniforme**, no aleatorio: la muestra tiene que
    ser la misma para todos los genomas de la ejecución (regla 2), y un reparto
    uniforme garantiza además la cobertura de todos los regímenes sin depender de
    la suerte de una semilla.

    `target_scored` es el total de velas puntuables que se quieren repartir entre
    los bloques. Es el mando que controla el coste: con él se decide cuánto se
    paga por evaluar un genoma, independientemente de lo largo que sea el
    histórico.

    Si el histórico no da para el plan pedido, se devuelve un único bloque con
    todo lo disponible: degradar a «usarlo entero» es correcto y es lo que ya
    hacía el motor antes de existir este módulo.
    """
    n_bars = int(n_bars)
    n_blocks = max(1, int(n_blocks))
    warmup = max(0, int(warmup))
    target = int(target_scored or n_bars)

    if n_bars <= 0:
        return []

    per_block = target // n_blocks
    # Un bloque más corto que su propio calentamiento no puntúa casi nada: mejor
    # menos bloques y más largos que muchos que solo miden su arranque.
    if per_block < max(60, warmup // 2) or n_bars < n_blocks * (per_block + warmup):
        return [Block(warmup_start=0, score_start=min(warmup, n_bars // 4), end=n_bars)]

    stride = n_bars // n_blocks
    blocks: list[Block] = []
    for k in range(n_blocks):
        score_start = k * stride
        # El primer bloque no tiene pasado del que cebarse; se le cede su propio
        # arranque como calentamiento en lugar de fingir que lo tiene.
        if score_start < warmup:
            score_start = warmup
        end = min(score_start + per_block, n_bars)
        if end - score_start < 30:
            continue
        blocks.append(Block(warmup_start=max(0, score_start - warmup),
                            score_start=score_start, end=end))
    return blocks or [Block(0, min(warmup, n_bars // 4), n_bars)]


def coverage_ratio(blocks: list[Block], n_bars: int) -> float:
    """
    Qué fracción del histórico ABARCA la muestra, de principio a fin.

    No es la fracción puntuada —eso es `sampled_ratio`— sino cuánto del eje
    temporal queda representado. Una muestra que puntúa el 20 % pero solo toca
    los primeros seis meses no vale; una que puntúa el 20 % repartido a lo largo
    de tres años, sí.
    """
    if not blocks or n_bars <= 0:
        return 0.0
    return (blocks[-1].end - blocks[0].score_start) / n_bars


def sampled_ratio(blocks: list[Block], n_bars: int) -> float:
    """Fracción de velas que realmente puntúan (proxy directo del coste)."""
    if not blocks or n_bars <= 0:
        return 0.0
    return sum(b.scored_bars for b in blocks) / n_bars


def evaluate_blocks(df, blocks: list[Block], backtest_fn) -> dict:
    """
    Backtestea cada bloque por separado y agrega los resultados.

    `backtest_fn(sub_df) -> dict` recibe el bloque CON su calentamiento y
    devuelve el resultado de un backtest normal. La agregación descarta los
    retornos del tramo de calentamiento y concatena los del tramo puntuable.

    Lo que NO se hace, y es lo importante: no se pegan los precios de los
    bloques. Entre el final de uno y el principio del siguiente puede haber
    meses, y unirlos crearía un salto de precio ficticio que el backtest leería
    como el movimiento más grande de la serie.
    """
    returns: list[float] = []
    trades: list[dict] = []
    total_bars = 0

    for block in blocks:
        sub = df.iloc[block.warmup_start:block.end]
        if len(sub) < 30:
            continue
        result = backtest_fn(sub)
        bar_returns = np.asarray(result.get("bar_returns", []), dtype=float)
        skip = block.score_start - block.warmup_start
        scored = bar_returns[skip:] if skip < bar_returns.size else np.array([])
        returns.extend(scored.tolist())
        total_bars += int(scored.size)
        # Solo las operaciones ABIERTAS en el tramo puntuable: las del
        # calentamiento existen para que los indicadores lleguen cebados, no
        # para contar como resultado.
        for t in result.get("trades", []):
            if t.get("entry_index", 0) >= skip:
                trades.append(t)

    return {
        "bar_returns": returns,
        "trades": trades,
        "n_blocks": len(blocks),
        "scored_bars": total_bars,
        "total_trades": len(trades),
    }


def describe(blocks: list[Block], n_bars: int) -> dict:
    """Resumen publicable de la muestra: qué se evaluó y qué parte del todo es."""
    if not blocks:
        return {"n_blocks": 0, "note": "Sin muestra: se evalúa el histórico completo."}
    scored = sum(b.scored_bars for b in blocks)
    cov = coverage_ratio(blocks, n_bars)
    return {
        "n_blocks": len(blocks),
        "scored_bars": scored,
        "total_bars": n_bars,
        "sampled_pct": round(sampled_ratio(blocks, n_bars) * 100.0, 1),
        "coverage_pct": round(cov * 100.0, 1),
        "blocks": [{"from": b.score_start, "to": b.end, "warmup": b.score_start - b.warmup_start}
                   for b in blocks],
        "note": (
            f"El fitness del buscador se calcula sobre {len(blocks)} bloques "
            f"({scored} de {n_bars} velas, {sampled_ratio(blocks, n_bars) * 100:.0f}%) "
            f"repartidos por el {cov * 100:.0f}% del histórico. Sirve para ORDENAR "
            "candidatas a coste acotado; el veredicto de cada finalista se calcula "
            "después sobre el histórico completo."
        ),
    }
