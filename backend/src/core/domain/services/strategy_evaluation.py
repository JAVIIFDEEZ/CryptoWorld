"""
strategy_evaluation.py — Evaluación robustez-aware de un StrategySpec.

Puente entre el generador genético y la suite de robustez (Módulo 1): compila
un spec a señales (Módulo 0), lo backtestea con el motor existente
(backtest_signals) e INVOCA las primitivas de robustez (Sharpe, Deflated
Sharpe, PBO/CSCV, Monte Carlo, detector de lookahead). No reimplementa ninguna
de esas matemáticas.

Tres niveles:
  - evaluate_fitness:  barato, para el fitness del GA (Sharpe OOS walk-forward
    con penalización de sobreajuste y de bajo nº de trades). NO usa retorno
    in-sample.
  - gate_spec:         caro, solo para finalistas: umbrales de PBO, lookahead,
    eficiencia walk-forward, percentil 5 de Monte Carlo y nº de trades.
  - holdout_performance: rendimiento en el tramo de validación final intacto.

Capa de dominio: Python puro.
"""

from dataclasses import dataclass

import numpy as np

from core.domain.services import backtest_metrics as metrics
from core.domain.services import backtest_robustness as robustness
from core.domain.services import backtest_bias as bias
from core.domain.services import block_sampling
from core.domain.services import market_impact as impact
from core.domain.services import meta_sizing
from core.domain.services import significance as sig
from core.domain.services.backtest_execution import CostModel
from core.domain.services.strategy_spec import compile_signals, jitter_params, spec_risk, spec_sizing
from core.domain.services.technical_analysis_service import backtest_signals

# Costes por defecto del generador: comisión 10 bps + deslizamiento 5 bps por lado
# (≈ taker de exchange cripto). Hace el fitness CONSCIENTE de costes: las
# estrategias que operan demasiado pierden su edge en comisiones y mueren solas.
DEFAULT_COSTS = CostModel(commission_bps=10.0, slippage_bps=5.0)


@dataclass(frozen=True)
class GatingThresholds:
    """Umbrales del gating de robustez (defaults sensatos, configurables)."""
    min_trades: int = 12
    max_pbo: float = 0.5
    min_wf_efficiency: float = 0.4
    min_mc_p5_pct: float = 0.0       # percentil 5 del retorno Monte Carlo > 0
    wf_splits: int = 4
    pbo_neighbors: int = 12
    mc_sims: int = 400
    # ── Validación cruzada combinatoria purgada (CPCV) ──
    # Se REPORTA, no bloquea: primero hay que ver la distribución sobre activos
    # reales para fijar un umbral con criterio. Convertirlo en check es añadir
    # `cpcv_p5` a `checks` con `min_cpcv_p5_sharpe`.
    cpcv_blocks: int = 8             # bloques contiguos del histórico
    cpcv_k: int = 2                  # bloques por camino → C(8,2) = 28 caminos
    cpcv_embargo_pct: float = 0.02   # velas descartadas al inicio de cada bloque
    # ── Overlay de convicción (meta-modelo → tamaño de posición) ──
    # Apagado por defecto A PROPÓSITO. Entrenar un meta-modelo cuesta ~1,4 s por
    # candidata sobre un histórico de 2000 velas, y el resultado no entra en
    # `checks`: no decide nada, se muestra. Pagarlo en cada intento del gating
    # —hasta 18 en el preset exhaustivo— es gastar minutos para enseñar una
    # tarjeta del campeón. El generador lo calcula sobre el RANKING ya
    # decidido, igual que hace con la cascada de retests.
    #
    # Se deja el interruptor porque `gate_spec` también se invoca suelto (API de
    # robustez de un spec concreto), donde sí hay una sola estrategia que medir.
    meta_sizing: bool = False


def _segment_backtest(df, spec: dict, costs: CostModel | None = None) -> dict:
    """Compila el spec y lo backtestea (con costes, gestión de riesgo y sizing)."""
    return backtest_signals(
        df, compile_signals(df, spec),
        costs=costs if costs is not None else DEFAULT_COSTS,
        risk=spec_risk(spec),
        sizing=spec_sizing(spec),
    )


def walk_forward_oos(df, spec: dict, n_splits: int = 4, ppy: float = 365.0, min_train: int = 60,
                     costs: CostModel | None = None) -> dict:
    """
    Walk-forward del spec FIJO (sin re-optimizar: el GA ya hace la búsqueda).
    Backtestea cada tramo OOS de forma independiente y agrega el Sharpe IS/OOS
    y la eficiencia OOS/IS. Reutiliza sharpe_ratio del Módulo 1.
    """
    n = len(df)
    fold = n // (n_splits + 1)
    is_sharpes, oos_sharpes, oos_returns, oos_trades = [], [], [], []
    if fold >= 20:
        for k in range(1, n_splits + 1):
            test_start = k * fold
            test_end = n if k == n_splits else (k + 1) * fold
            train = df.iloc[:test_start]
            test = df.iloc[test_start:test_end]
            if len(train) < min_train or len(test) < 20:
                continue
            bt_is = _segment_backtest(train, spec, costs)
            bt_oos = _segment_backtest(test, spec, costs)
            is_sharpes.append(metrics.sharpe_ratio(bt_is["bar_returns"], ppy))
            oos_sharpes.append(metrics.sharpe_ratio(bt_oos["bar_returns"], ppy))
            oos_returns.extend(bt_oos["bar_returns"])
            oos_trades.extend(bt_oos["trades"])

    mean_is = float(np.mean(is_sharpes)) if is_sharpes else 0.0
    mean_oos = float(np.mean(oos_sharpes)) if oos_sharpes else 0.0
    if mean_is > 1e-9:
        efficiency = mean_oos / mean_is
    else:
        # Sharpe IS ≤ 0: el cociente no tiene sentido. Si aun así el OOS es
        # positivo, la estrategia GENERALIZA (no hay sobreajuste que medir):
        # eficiencia 1.0. Antes se forzaba a 0 y el gating la mataba injustamente.
        efficiency = 1.0 if mean_oos > 0 else 0.0
    return {
        "mean_is_sharpe": round(mean_is, 4),
        "mean_oos_sharpe": round(mean_oos, 4),
        "efficiency": round(float(efficiency), 4),
        "oos_returns": oos_returns,
        "oos_trades": oos_trades,
        "n_folds": len(oos_sharpes),
        "fold_oos_sharpes": [round(float(s), 4) for s in oos_sharpes],
    }


def purged_cpcv(df, spec: dict, n_blocks: int = 8, k: int = 2, embargo_pct: float = 0.02,
                ppy: float = 365.0, costs: CostModel | None = None) -> dict:
    """
    Validación cruzada combinatoria purgada del spec (CPCV).

    El walk-forward recorre UN camino histórico y devuelve un punto con mucha
    varianza. Aquí el histórico se parte en `n_blocks` bloques contiguos, cada
    uno se backtestea de forma independiente, y se agregan todas las
    combinaciones de `k` bloques: el resultado es una **distribución** de Sharpe
    sobre C(n_blocks, k) caminos.

    Sobre la purga, que aquí no significa lo que en el libro
    ─────────────────────────────────────────────────────────────────────
    El *purging* de López de Prado quita del ENTRENAMIENTO las muestras cuyas
    etiquetas solapan con el test, porque el modelo se ajusta sobre el train y
    ese solape es la fuga. En este motor **no se ajusta nada** en el walk-forward:
    el spec ya viene fijo del GA y cada tramo se backtestea aislado. Purgar el
    train, por tanto, no cerraría ninguna fuga — solo cambiaría el Sharpe IS.

    Lo que sí es una fuente real de contaminación aquí es la **frontera entre
    bloques**: las primeras velas de un bloque tienen los indicadores a medio
    calentar y cualquier señal en ellas se calcula sobre una ventana incompleta.
    El `embargo_pct` descarta esas velas iniciales de cada bloque. Ese es el
    análogo que hace algo, y es lo que se implementa.

    Cada bloque se backtestea SIN prefijo de datos de bloques vecinos: esa es la
    purga efectiva — ningún bloque ve información de otro.
    """
    n = len(df)
    n_blocks = max(2, int(n_blocks))
    block_size = n // n_blocks
    if block_size < 30:
        return {"n_paths": 0, "n_blocks": 0,
                "note": ("Histórico insuficiente para la validación combinatoria "
                         f"({n} velas para {n_blocks} bloques).")}

    embargo_bars = max(1, int(round(block_size * max(0.0, embargo_pct))))

    block_returns: list = []
    block_stats: list[dict] = []
    for b in range(n_blocks):
        start = b * block_size
        end = n if b == n_blocks - 1 else (b + 1) * block_size
        segment = df.iloc[start:end]
        if len(segment) <= embargo_bars + 5:
            continue
        bt = _segment_backtest(segment, spec, costs)
        # Embargo: fuera las primeras velas del bloque (indicadores calentando y
        # cualquier lectura a caballo del corte).
        returns = list(bt["bar_returns"])[embargo_bars:]
        if len(returns) < 5:
            continue
        block_returns.append(returns)
        block_stats.append({
            "block": b + 1,
            "candles": len(returns),
            "sharpe": round(metrics.sharpe_ratio(returns, ppy), 3),
            "n_trades": bt["total_trades"],
        })

    result = robustness.combinatorial_paths(block_returns, k=k, ppy=ppy)
    result["embargo_pct"] = embargo_pct
    result["embargo_bars"] = embargo_bars
    result["blocks"] = block_stats
    result["purge_note"] = (
        "Cada bloque se backtestea aislado (ningún bloque ve datos de otro) y se "
        "descartan sus primeras velas por embargo. No se purga el train al modo "
        "del libro porque aquí no se entrena nada: el spec viene fijo del "
        "buscador, así que esa purga no cerraría ninguna fuga."
    )
    return result


def noise_test(df, spec: dict, n_runs: int = 10, atr_fraction: float = 0.25,
               ppy: float = 365.0, seed: int = 42, costs: CostModel | None = None) -> dict:
    """
    ¿La estrategia depende de los precios EXACTOS que ocurrieron?

    Se perturba el OHLC con ruido proporcional al ATR y se reevalúa. El pasado
    es una realización de un proceso, no la única que podía haber ocurrido: una
    estrategia con edge real tolera que las velas hubieran sido ligeramente
    distintas, y una ajustada a la curva se desploma porque vivía de máximos y
    mínimos concretos. Es el retest más citado de StrategyQuant
    (*randomize history*) y ataca el curve fitting de frente.

    El ruido respeta la coherencia de la vela: tras perturbar, se recomponen
    `high` y `low` como envolvente de apertura y cierre, de modo que ninguna
    vela queda con máximo por debajo del cierre.
    """
    import pandas as pd

    close = df["close"].to_numpy(dtype=float)
    if close.size < 30:
        return {"n_runs": 0, "note": "Serie insuficiente para el test de ruido."}

    high = df["high"].to_numpy(dtype=float) if "high" in df else close
    low = df["low"].to_numpy(dtype=float) if "low" in df else close
    open_ = df["open"].to_numpy(dtype=float) if "open" in df else close

    # ATR simplificado (rango medio de la vela): la escala natural del ruido.
    atr = float(np.mean(high - low))
    if not np.isfinite(atr) or atr <= 0:
        atr = float(np.mean(np.abs(np.diff(close)))) if close.size > 1 else 0.0
    amplitude = atr * max(0.0, atr_fraction)
    if amplitude <= 0:
        return {"n_runs": 0, "note": "Sin volatilidad medible para escalar el ruido."}

    base = metrics.sharpe_ratio(_segment_backtest(df, spec, costs)["bar_returns"], ppy)
    rng = np.random.default_rng(seed)
    sharpes: list[float] = []

    for _ in range(max(1, n_runs)):
        shock = rng.normal(0.0, amplitude, close.size)
        nc = np.maximum(close + shock, 1e-9)
        no = np.maximum(open_ + rng.normal(0.0, amplitude, close.size), 1e-9)
        # Envolvente coherente: el máximo nunca por debajo del cuerpo de la vela.
        nh = np.maximum.reduce([high + shock, nc, no])
        nl = np.minimum.reduce([np.maximum(low + shock, 1e-9), nc, no])
        noisy = pd.DataFrame({
            "timestamp": df["timestamp"].values if "timestamp" in df else np.arange(close.size),
            "open": no, "high": nh, "low": nl, "close": nc,
            "volume": df["volume"].values if "volume" in df else np.ones(close.size),
        })
        # El coste de financiación viaja con la serie perturbada: lo que se
        # altera aquí son los precios, no lo que costaba mantener la posición.
        # Reconstruir el DataFrame sin esta columna dejaría a las ejecuciones
        # ruidosas operando gratis contra una base que sí paga, y la
        # degradación medida saldría artificialmente baja.
        if "funding_rate" in df:
            noisy["funding_rate"] = df["funding_rate"].values
        sharpes.append(metrics.sharpe_ratio(_segment_backtest(noisy, spec, costs)["bar_returns"], ppy))

    arr = np.array(sharpes, dtype=float)
    return {
        "n_runs": int(arr.size),
        "atr_fraction": atr_fraction,
        "base_sharpe": round(float(base), 3),
        "noisy_sharpe_mean": round(float(arr.mean()), 3),
        "noisy_sharpe_median": round(float(np.median(arr)), 3),
        "noisy_sharpe_p5": round(float(np.percentile(arr, 5)), 3),
        "pct_runs_positive": round(float((arr > 0).mean() * 100), 1),
        # Cuánto del Sharpe se evapora al mover las velas. Alto = la estrategia
        # vivía de precios concretos.
        "degradation_pct": round(
            float((base - np.median(arr)) / abs(base) * 100) if abs(base) > 1e-9 else 0.0, 1
        ),
    }


def starting_bar_test(df, spec: dict, offsets=(0, 5, 11, 23, 37), ppy: float = 365.0,
                      costs: CostModel | None = None) -> dict:
    """
    ¿El resultado depende de dónde se empezó a mirar?

    Se recorta el arranque de la serie en distintos desplazamientos y se
    reevalúa. Una estrategia sólida da resultados parecidos empiece donde
    empiece; una que solo funciona con un alineamiento concreto del histórico
    delata que su rendimiento venía de la casualidad de por dónde se cortó.
    """
    sharpes: list[dict] = []
    for off in offsets:
        off = int(off)
        if off < 0 or len(df) - off < 60:
            continue
        segment = df.iloc[off:].reset_index(drop=True)
        s = metrics.sharpe_ratio(_segment_backtest(segment, spec, costs)["bar_returns"], ppy)
        sharpes.append({"offset": off, "sharpe": round(float(s), 3)})

    if not sharpes:
        return {"n_offsets": 0, "note": "Serie insuficiente para variar el arranque."}

    values = np.array([s["sharpe"] for s in sharpes], dtype=float)
    return {
        "n_offsets": len(sharpes),
        "results": sharpes,
        "sharpe_mean": round(float(values.mean()), 3),
        "sharpe_std": round(float(values.std(ddof=1)) if values.size > 1 else 0.0, 3),
        "sharpe_min": round(float(values.min()), 3),
        "pct_offsets_positive": round(float((values > 0).mean() * 100), 1),
    }


def skip_trades_test(trades: list, skip_pct: float = 0.1, n_runs: int = 200,
                     seed: int = 42) -> dict:
    """
    ¿Sobrevive si se pierde una parte de las operaciones?

    En real se fallan ejecuciones: hay desconexiones, órdenes rechazadas y
    momentos en que no se estaba mirando. Se descarta al azar un `skip_pct` de
    los trades y se mide el P&L resultante. Si el resultado depende de haber
    capturado TODAS las operaciones —típico de estrategias cuyo beneficio se
    concentra en unos pocos aciertos—, la distribución se hunde.
    """
    pnls = [float(t.get("pnl_pct", 0.0)) for t in (trades or [])]
    if len(pnls) < 5:
        return {"n_runs": 0, "note": "Muy pocas operaciones para el test de omisión."}

    rng = np.random.default_rng(seed)
    keep = max(1, int(round(len(pnls) * (1.0 - max(0.0, min(skip_pct, 0.9))))))
    totals: list[float] = []
    arr = np.array(pnls, dtype=float)
    for _ in range(max(1, n_runs)):
        idx = rng.choice(arr.size, size=keep, replace=False)
        totals.append(float(arr[idx].sum()))

    dist = np.array(totals, dtype=float)
    full_total = float(arr.sum())
    return {
        "n_runs": int(dist.size),
        "skip_pct": skip_pct,
        "trades_total": int(arr.size),
        "trades_kept": keep,
        "full_pnl_pct": round(full_total, 2),
        "pnl_median_pct": round(float(np.median(dist)), 2),
        "pnl_p5_pct": round(float(np.percentile(dist, 5)), 2),
        "pct_runs_profitable": round(float((dist > 0).mean() * 100), 1),
    }


def retest_cascade(df, spec: dict, trades: list | None = None, ppy: float = 365.0,
                   seed: int = 42, costs: CostModel | None = None,
                   noise_runs: int = 10) -> dict:
    """
    Cascada de retests al estilo StrategyQuant, con un veredicto agregado.

    Cada prueba ataca una forma distinta de sobreajuste:
      · ruido en los precios → dependencia de los datos exactos;
      · desplazamiento del arranque → dependencia del corte del histórico;
      · omisión de operaciones → dependencia de capturarlas todas;
      · sensibilidad paramétrica → dependencia del parámetro exacto;
      · estabilidad temporal → ¿el beneficio está repartido, o fue una racha?

    Se reporta además el rendimiento por régimen de volatilidad: un edge que
    solo vive en mercados turbulentos sigue siendo un edge, pero conviene
    saberlo antes de asignarle capital.

    `survived` resume si la estrategia aguanta las cinco. Se REPORTA: no
    recorta el ranking. Convertirlo en filtro es usar este booleano.

    Si no se pasan `trades`, se recalculan aquí: un backtest más es barato al
    lado de los ~15 que cuesta la cascada, y evita arrastrar la lista completa
    de operaciones por el payload solo para esto.
    """
    if trades is None:
        trades = _segment_backtest(df, spec, costs)["trades"]

    from core.domain.services import regime as regime_svc

    noise = noise_test(df, spec, n_runs=noise_runs, ppy=ppy, seed=seed, costs=costs)
    starting = starting_bar_test(df, spec, ppy=ppy, costs=costs)
    skipping = skip_trades_test(trades or [], seed=seed)
    sensitivity = parameter_sensitivity(df, spec, ppy=ppy, seed=seed, costs=costs)

    # Estabilidad temporal y reparto por régimen: un beneficio concentrado en un
    # tramo no es un edge, es una racha — y ningún walk-forward que promedie
    # tramos lo delata, porque el promedio es justo lo que lo esconde.
    full = _segment_backtest(df, spec, costs)
    stability = regime_svc.temporal_stability(full["bar_returns"])
    regimes = regime_svc.detect_regimes(df["close"].to_numpy(dtype=float))
    by_regime = (regime_svc.performance_by_regime(full["bar_returns"], regimes["labels"])
                 if regimes.get("n") else {"note": "Serie insuficiente para clasificar regímenes."})

    # Cada criterio se da por superado si la prueba pudo ejecutarse Y el
    # resultado aguanta. Una prueba que no pudo correr no cuenta como fallo:
    # ausencia de evidencia no es evidencia de fragilidad.
    checks = {
        "noise": noise.get("n_runs", 0) == 0 or noise.get("pct_runs_positive", 0) >= 60.0,
        "starting_bar": (starting.get("n_offsets", 0) == 0
                         or starting.get("pct_offsets_positive", 0) >= 60.0),
        "skip_trades": (skipping.get("n_runs", 0) == 0
                        or skipping.get("pct_runs_profitable", 0) >= 60.0),
        "parameter_sensitivity": (sensitivity.get("n_neighbors", 0) == 0
                                  or sensitivity.get("pct_neighbors_positive", 0) >= 50.0),
        "temporal_stability": stability.get("n_buckets", 0) == 0 or bool(stability.get("stable")),
    }
    failed = [name for name, ok in checks.items() if not ok]

    return {
        "survived": not failed,
        "checks": checks,
        "failed": failed,
        "noise": noise,
        "starting_bar": starting,
        "skip_trades": skipping,
        "parameter_sensitivity": sensitivity,
        "temporal_stability": stability,
        "by_regime": by_regime,
        "note": (
            "Sobrevive a todas las perturbaciones: ruido en los precios, "
            "desplazamiento del arranque, omisión de operaciones, cambio de "
            "parámetros y reparto del beneficio en el tiempo."
            if not failed else
            "Falla en: " + ", ".join(failed) + ". El resultado depende de "
            "condiciones concretas del histórico más de lo que un edge real debería."
        ),
    }


def walk_forward_matrix(df, spec: dict, splits_list=(3, 4, 5, 6),
                        ppy: float = 365.0, costs: CostModel | None = None) -> dict:
    """
    Matriz walk-forward (estilo StrategyQuant): re-ejecuta el walk-forward del
    spec con DISTINTOS números de particiones y expone el Sharpe OOS de CADA
    tramo. Una estrategia estable es rentable en la mayoría de celdas sea cual
    sea el troceo; una frágil solo brilla con una partición concreta (síntoma de
    ajuste a un periodo). Es la radiografía de estabilidad temporal del campeón.
    """
    rows = []
    for n in splits_list:
        wf = walk_forward_oos(df, spec, n_splits=int(n), ppy=ppy, costs=costs)
        rows.append({
            "n_splits": int(n),
            "folds": wf["fold_oos_sharpes"],
            "mean_oos_sharpe": wf["mean_oos_sharpe"],
            "efficiency": wf["efficiency"],
        })
    all_folds = [f for r in rows for f in r["folds"]]
    positive = sum(1 for f in all_folds if f > 0)
    return {
        "rows": rows,
        "total_folds": len(all_folds),
        "positive_folds": positive,
        "stability_score": round(positive / len(all_folds), 3) if all_folds else 0.0,
        "note": ("Sharpe OOS de cada tramo walk-forward bajo distintos troceos. "
                 "Estable = mayoría de celdas positivas con cualquier partición."),
    }


def spec_complexity(spec: dict) -> int:
    """Nº total de condiciones del spec (entrada + salida): su 'tamaño genético'."""
    return len(spec.get("entry", {}).get("conditions", [])) + \
        len(spec.get("exit", {}).get("conditions", []))


def equity_curve(df, spec: dict, costs: CostModel | None = None, points: int = 120) -> dict:
    """
    Curva de equity normalizada (base 1.0) del spec sobre `df`, submuestreada a
    ≤ `points` puntos: alimenta la telemetría visual en vivo del generador sin
    inflar el payload. Devuelve además las métricas de cabecera de la curva.
    """
    bt = _segment_backtest(df, spec, costs)
    r = np.asarray(bt["bar_returns"], dtype=float)
    eq = np.concatenate([[1.0], np.cumprod(1.0 + r)])
    if eq.size > points:
        idx = np.linspace(0, eq.size - 1, points).astype(int)
        eq = eq[idx]
    return {
        "equity": [round(float(v), 5) for v in eq],
        "total_return_pct": bt["total_return_pct"],
        "max_drawdown_pct": bt["max_drawdown_pct"],
        "n_trades": bt["total_trades"],
    }


def returns_series(df, spec: dict, costs: CostModel | None = None) -> np.ndarray:
    """Serie completa de retornos por vela del spec sobre `df` (para medir la
    correlación entre estrategias: un libro institucional quiere finalistas
    DECORRELACIONADAS, no clones del mismo edge)."""
    return np.asarray(_segment_backtest(df, spec, costs)["bar_returns"], dtype=float)


def _fitness_on_blocks(df, spec, blocks, n_splits, ppy, min_trades, target_trades,
                       costs, parsimony, with_returns) -> dict:
    """
    Fitness sobre la muestra de bloques.

    Cada bloque hace de tramo fuera de muestra por sí mismo: son tramos
    DISJUNTOS del histórico, así que el Sharpe de cada uno mide el spec sobre
    datos que no comparten con los demás. Eso es lo que sustituye aquí al
    walk-forward — y es una sustitución legítima porque el walk-forward, en este
    punto, tampoco entrena nada: el spec ya viene fijo del GA.

    La penalización por sobreajuste cambia de forma en consecuencia: sin tramo
    «in-sample» que comparar, se usa la DISPERSIÓN entre bloques. Una estrategia
    que rinde igual en los seis tramos es preferible a otra con la misma media y
    un único bloque llevándose todo el mérito — que es la firma de haber
    encontrado un tramo afortunado, no un edge.
    """
    # ── Los umbrales de operaciones se escalan con la muestra ────────
    # Sin esto, exigir 25 operaciones sobre el 15 % de las velas equivale a
    # exigir ~167 sobre el histórico completo: casi todo genoma cae en la
    # penalización, el fitness pasa a medir «quién opera más» y el orden
    # resultante ANTICORRELACIONA con el del histórico entero (medido: Spearman
    # −0.38 antes de esta corrección). Es el error que hace inútil un muestreo
    # por lo demás correcto.
    scored = sum(b.scored_bars for b in blocks)
    fraction = scored / len(df) if len(df) else 1.0
    scaled_target = max(4, int(round(target_trades * fraction)))
    scaled_min = max(2, int(round(min_trades * fraction)))

    agg = block_sampling.evaluate_blocks(
        df, blocks, lambda sub: _segment_backtest(sub, spec, costs))

    returns = np.asarray(agg["bar_returns"], dtype=float)
    n_trades = agg["total_trades"]
    if returns.size < 30:
        return {"fitness": -5.0, "mean_oos_sharpe": 0.0, "mean_is_sharpe": 0.0,
                "efficiency": 0.0, "overfit_gap": 0.0, "n_trades": n_trades,
                "total_return_pct": 0.0, "max_drawdown_pct": 0.0, "turnover": 0.0,
                "cost_drag_pct": 0.0, "complexity": spec_complexity(spec),
                "n_blocks": agg["n_blocks"], "source": "blocks",
                **({"bar_returns": []} if with_returns else {})}

    per_block: list[float] = []
    for block in blocks:
        sub = df.iloc[block.warmup_start:block.end]
        if len(sub) < 30:
            continue
        bt = _segment_backtest(sub, spec, costs)
        skip = block.score_start - block.warmup_start
        br = np.asarray(bt["bar_returns"], dtype=float)[skip:]
        if br.size >= 20:
            per_block.append(metrics.sharpe_ratio(br, ppy))

    mean_sharpe = float(np.mean(per_block)) if per_block else 0.0
    # Dispersión entre bloques: castiga que el resultado dependa de un tramo.
    dispersion = float(np.std(per_block)) if len(per_block) > 1 else 0.0

    trade_penalty = 0.0 if n_trades >= scaled_target else (scaled_target - n_trades) / scaled_target
    complexity_penalty = parsimony * max(0, spec_complexity(spec) - 3)

    fitness = mean_sharpe - 0.5 * dispersion - 1.0 * trade_penalty - complexity_penalty
    if n_trades < scaled_min or not per_block:
        fitness -= 3.0

    result = {
        "fitness": round(float(fitness), 4),
        "mean_oos_sharpe": round(mean_sharpe, 4),
        "mean_is_sharpe": round(mean_sharpe, 4),
        "efficiency": 1.0,
        "overfit_gap": round(dispersion, 4),
        "n_trades": n_trades,
        "total_return_pct": round(float((np.prod(1.0 + returns) - 1.0) * 100.0), 2),
        "max_drawdown_pct": 0.0,
        "turnover": 0.0,
        "cost_drag_pct": 0.0,
        "complexity": spec_complexity(spec),
        # De dónde sale este número. Un fitness de bloques y uno de histórico
        # completo NO son comparables entre ejecuciones, y callarlo invitaría a
        # compararlos.
        "source": "blocks",
        "n_blocks": len(per_block),
        "block_sharpe_dispersion": round(dispersion, 4),
        "sampled_fraction": round(fraction, 4),
        "scaled_target_trades": scaled_target,
    }
    if with_returns:
        result["bar_returns"] = agg["bar_returns"]
    return result


def evaluate_fitness(
    df,
    spec: dict,
    n_splits: int = 4,
    ppy: float = 365.0,
    min_trades: int = 8,
    target_trades: int = 25,
    costs: CostModel | None = None,
    parsimony: float = 0.0,
    with_returns: bool = False,
    blocks: list | None = None,
) -> dict:
    """
    Fitness robustez-aware (NO retorno in-sample): Sharpe OOS del walk-forward
    NETO de costes, penalizando el sobreajuste (gap Sharpe IS−OOS), el bajo nº de
    operaciones y la rotación excesiva (que en datos reales sangra en comisiones).
    `parsimony` > 0 añade presión de simplicidad al estilo StrategyQuant: cada
    condición por encima de 3 resta `parsimony` al fitness (a igual rendimiento,
    gana la estrategia más simple — menos grados de libertad, menos sobreajuste).

    `with_returns=True` añade `bar_returns` al resultado. El backtest ya la ha
    calculado, así que devolverla es gratis y evita repetirlo: es lo que permite
    al buscador quedarse con las series de los genomas que evalúa y alimentar
    con ellas el PBO y el Deflated Sharpe.

    `blocks` activa la evaluación por muestreo de bloques (`block_sampling`). El
    fitness solo tiene que ORDENAR genomas entre sí —el veredicto lo da el
    gating sobre el histórico completo—, y ordenar bien no exige medirlo todo.
    Es lo que permite buscar sobre años de datos sin pagar años de cómputo: sin
    ello, el coste del GA es lineal en velas y tres años de gráficos horarios
    llevarían la búsqueda a más de dos horas.
    """
    if blocks:
        return _fitness_on_blocks(df, spec, blocks, n_splits, ppy, min_trades,
                                  target_trades, costs, parsimony, with_returns)

    full = _segment_backtest(df, spec, costs)
    n_trades = full["total_trades"]
    wf = walk_forward_oos(df, spec, n_splits, ppy, costs=costs)

    mean_oos = wf["mean_oos_sharpe"]
    overfit_gap = max(0.0, wf["mean_is_sharpe"] - mean_oos)
    trade_penalty = 0.0 if n_trades >= target_trades else (target_trades - n_trades) / target_trades
    # Penalización suave de rotación excesiva (complementa a los costes ya aplicados)
    turnover_penalty = max(0.0, full["turnover"] - 30.0) * 0.02
    complexity_penalty = parsimony * max(0, spec_complexity(spec) - 3)

    fitness = mean_oos - 0.5 * overfit_gap - 1.0 * trade_penalty - turnover_penalty - complexity_penalty
    if n_trades < min_trades or wf["n_folds"] == 0:
        fitness -= 3.0  # estrategias degeneradas (casi sin operar) mueren

    result = {
        "fitness": round(float(fitness), 4),
        "mean_oos_sharpe": mean_oos,
        "mean_is_sharpe": wf["mean_is_sharpe"],
        "efficiency": wf["efficiency"],
        "overfit_gap": round(float(overfit_gap), 4),
        "n_trades": n_trades,
        "total_return_pct": full["total_return_pct"],
        "max_drawdown_pct": full["max_drawdown_pct"],
        "turnover": full["turnover"],
        "cost_drag_pct": full["total_commission_pct"],
        "complexity": spec_complexity(spec),
    }
    if with_returns:
        result["bar_returns"] = full["bar_returns"]
    return result


def _neighborhood_returns(df, spec: dict, k: int, rng: np.random.Generator,
                          costs: CostModel | None = None) -> list:
    """Series de retorno del spec y de k−1 vecinos con parámetros perturbados.

    OJO con qué es y qué no es esto. Son perturbaciones ±% de UNA estrategia ya
    elegida, es decir casi clones entre sí: sirven para medir **sensibilidad
    paramétrica** (¿el resultado depende de haber acertado el parámetro exacto?),
    que es un test de robustez legítimo y el que StrategyQuant llama
    *randomize parameters*.

    Lo que NO son es la población de pruebas del *False Strategy Theorem*. Al ser
    casi idénticas su varianza de Sharpe tiende a 0, y con ella el umbral
    E[max SR₀] → 0, de modo que el Deflated Sharpe calculado sobre ellas sale
    ≈1 para casi cualquier estrategia: no mide nada. Esa deflación necesita las
    series de los genomas que el GA evaluó de verdad, que llegan a `gate_spec`
    por `trial_returns`.
    """
    columns = [_segment_backtest(df, spec, costs)["bar_returns"]]
    for _ in range(k - 1):
        neighbor = jitter_params(spec, rng)
        columns.append(_segment_backtest(df, neighbor, costs)["bar_returns"])
    length = min(len(c) for c in columns)
    if length < 8 or len(columns) < 2:
        return []
    return [list(c[:length]) for c in columns]


def _stack_returns(columns: list):
    """Lista de series de igual longitud → matriz (T, N); None si no da."""
    if not columns or len(columns) < 2:
        return None
    length = min(len(c) for c in columns)
    if length < 8:
        return None
    return np.column_stack([np.asarray(c[:length], dtype=float) for c in columns])


def _overfitting_control(df, spec: dict, spec_returns, th, rng, ppy: float,
                         costs: CostModel | None, trial_returns: list | None,
                         n_evaluations: int | None) -> dict:
    """
    Bloque de control de sobreajuste: PBO (CSCV) + Deflated Sharpe + la curva
    E[max SR₀] frente al nº de pruebas.

    La fuente de la matriz decide qué significan los números, así que se declara
    explícitamente en `source`:
      · `search_trials` — series de los genomas realmente evaluados. El PBO mide
        sobreajuste de selección y el DSR se deflacta por el N real. Es el modo
        institucional.
      · `parameter_jitter` — perturbaciones del propio spec, cuando quien llama
        no aporta trials (uso suelto de `gate_spec`). Mide estabilidad local; el
        DSR resultante es optimista por construcción y se marca como tal.
    """
    sampled = [tr for tr in (trial_returns or []) if tr is not None and len(tr) >= 8]
    source = "search_trials" if len(sampled) >= 2 else "parameter_jitter"

    if source == "parameter_jitter":
        sampled = _neighborhood_returns(df, spec, th.pbo_neighbors, rng, costs)

    matrix = _stack_returns(sampled)
    pbo = (robustness.probability_of_backtest_overfitting(matrix)
           if matrix is not None else {"pbo": None, "note": "Trials insuficientes para PBO."})

    dsr = robustness.deflated_sharpe_ratio(
        spec_returns, sampled,
        # El recuento declarado solo tiene sentido con los trials de la búsqueda:
        # con jitter, N es literalmente el nº de vecinos generados.
        n_trials=n_evaluations if source == "search_trials" else None,
    )
    effective = robustness.effective_number_of_trials(sampled)

    curve = robustness.expected_max_sharpe_curve(
        variance=dsr.get("trial_sr_variance", 0.0) or 0.0,
        n_trials=dsr.get("n_trials", 1) or 1,
        observed_sharpe=dsr.get("sr_per_period"),
    )

    return {
        "source": source,
        "pbo": pbo,
        "deflated_sharpe": dsr,
        "effective_trials": effective,
        "expected_max_sharpe_curve": curve,
        "note": (
            "PBO y Deflated Sharpe calculados sobre los genomas realmente "
            "evaluados por la búsqueda: miden sobreajuste de selección y "
            "deflactan por el nº de pruebas."
            if source == "search_trials" else
            "Sin trials de búsqueda disponibles: PBO y DSR se calculan sobre "
            "perturbaciones del propio spec. Miden estabilidad paramétrica, NO "
            "sobreajuste de selección, y el DSR es optimista por construcción."
        ),
    }


def parameter_sensitivity(df, spec: dict, k: int = 12, ppy: float = 365.0,
                          seed: int = 42, costs: CostModel | None = None) -> dict:
    """
    Sensibilidad paramétrica: ¿cuánto se degrada la estrategia si sus parámetros
    se mueven un poco? Una estrategia con edge real tolera el zarandeo; una
    sobreajustada vive en un pico estrecho y se desploma.

    Es el uso correcto del jitter que antes alimentaba al PBO. Se reporta la
    dispersión del Sharpe entre vecinos y qué fracción de ellos sigue en
    positivo — no un veredicto de sobreajuste de selección, que es otra cosa.
    """
    rng = np.random.default_rng(seed)
    columns = _neighborhood_returns(df, spec, max(2, k), rng, costs)
    if not columns:
        return {"n_neighbors": 0, "note": "Serie insuficiente para el análisis de sensibilidad."}

    sharpes = np.array([metrics.sharpe_ratio(c, ppy) for c in columns], dtype=float)
    base = float(sharpes[0])          # la primera columna es el spec sin perturbar
    neighbors = sharpes[1:]
    if neighbors.size == 0:
        return {"n_neighbors": 0, "note": "Sin vecinos evaluables."}

    return {
        "n_neighbors": int(neighbors.size),
        "base_sharpe": round(base, 3),
        "neighbor_sharpe_mean": round(float(neighbors.mean()), 3),
        "neighbor_sharpe_std": round(float(neighbors.std(ddof=1)) if neighbors.size > 1 else 0.0, 3),
        "neighbor_sharpe_p5": round(float(np.percentile(neighbors, 5)), 3),
        "pct_neighbors_positive": round(float((neighbors > 0).mean() * 100), 1),
        # Caída relativa del vecino mediano frente al spec elegido: si es grande,
        # el resultado dependía de haber dado con el parámetro exacto.
        "median_degradation_pct": round(
            float((base - np.median(neighbors)) / abs(base) * 100) if abs(base) > 1e-9 else 0.0, 1
        ),
    }


def spec_permutation_test(
    df,
    spec: dict,
    observed_sharpe: float,
    n_perms: int = 120,
    ppy: float = 365.0,
    seed: int = 42,
) -> dict:
    """
    Test de permutación para un spec fijo: baraja los retornos de la serie de
    precios (destruye la estructura temporal), recompila las señales del spec y
    recalcula el Sharpe. Si el edge es real, el Sharpe observado supera al de la
    mayoría de permutaciones (p-valor bajo). Mismo método que el de las 5
    estrategias, pero compilando el spec componible en vez de una estrategia con
    nombre.
    """
    close = df["close"].values.astype(float)
    if close.size < 30 or np.any(close <= 0):
        return {"p_value": None, "observed_sharpe": round(float(observed_sharpe), 3),
                "n_perms": 0, "significant": False,
                "note": "Serie insuficiente para el test de permutación."}

    log_ret = np.diff(np.log(close))
    rng = np.random.default_rng(seed)
    count_ge = 0
    for _ in range(n_perms):
        perm = rng.permutation(log_ret)
        prices = close[0] * np.exp(np.concatenate([[0.0], np.cumsum(perm)]))
        pdf = df.copy()
        pdf["open"] = prices
        pdf["high"] = prices * 1.001
        pdf["low"] = prices * 0.999
        pdf["close"] = prices
        bt = backtest_signals(pdf, compile_signals(pdf, spec))
        s = metrics.sharpe_ratio(bt["bar_returns"], ppy)
        if s >= observed_sharpe:
            count_ge += 1

    p_value = (count_ge + 1) / (n_perms + 1)
    return {
        "p_value": round(float(p_value), 4),
        "observed_sharpe": round(float(observed_sharpe), 3),
        "n_perms": n_perms,
        "significant": bool(p_value < 0.05),
    }


def gate_spec(
    df,
    spec: dict,
    thresholds: GatingThresholds | None = None,
    ppy: float = 365.0,
    seed: int = 42,
    costs: CostModel | None = None,
    trial_returns: list | None = None,
    n_evaluations: int | None = None,
) -> dict:
    """
    Gating de robustez de una finalista (Módulo 1). Pasa si: sin lookahead,
    nº de trades ≥ mínimo, eficiencia walk-forward ≥ umbral, PBO ≤ umbral y
    percentil 5 de Monte Carlo > umbral. Devuelve checks + métricas completas.
    Todas las cifras son NETAS de costes y aplican la gestión de riesgo del spec.

    `trial_returns` son las series de retorno de los genomas que el buscador
    evaluó realmente, y `n_evaluations` cuántos evaluó en total (que puede ser
    mayor: quien llama muestrea para no guardarlo todo). Con ellas, el PBO mide
    sobreajuste **de selección** —el riesgo real de elegir a la mejor de muchas—
    y el Deflated Sharpe se deflacta por el nº de pruebas efectivamente hechas,
    que es lo que exige el *False Strategy Theorem*.

    Sin ellas se cae a las perturbaciones del propio spec. Ese modo mide
    estabilidad local, no sobreajuste de selección, y queda marcado como tal en
    `overfitting.source` para que ninguna superficie lo presente como algo que
    no es.
    """
    th = thresholds or GatingThresholds()
    rng = np.random.default_rng(seed)

    full = _segment_backtest(df, spec, costs)
    n_trades = full["total_trades"]
    wf = walk_forward_oos(df, spec, th.wf_splits, ppy, costs=costs)

    lookahead = bias.detect_lookahead_bias(df, lambda d: compile_signals(d, spec), seed=seed)

    overfitting = _overfitting_control(
        df, spec, full["bar_returns"], th, rng, ppy, costs, trial_returns, n_evaluations
    )
    pbo = overfitting["pbo"]

    # Distribución de rendimiento sobre múltiples caminos históricos, no el
    # punto único del walk-forward. Reportado, no bloqueante.
    cpcv = purged_cpcv(df, spec, n_blocks=th.cpcv_blocks, k=th.cpcv_k,
                       embargo_pct=th.cpcv_embargo_pct, ppy=ppy, costs=costs)

    # Capacidad: cuánto dinero admite este edge antes de que su propio impacto
    # de mercado se lo coma. Es una propiedad tan real de la estrategia como su
    # Sharpe, y la que ningún backtest retail reporta.
    capacity = impact.estimate_capacity(
        full["bar_returns"], full["trades"],
        adv_usd=impact.average_daily_volume_usd(df),
        daily_volatility=impact.daily_volatility_of(df),
    )

    # Separación dirección/tamaño: el spec dice DÓNDE entrar, el meta-modelo
    # CUÁNTO. Se mide fuera de muestra y solo se declara aplicable si supera al
    # primario; una estrategia que no admite modulación no es peor por ello.
    meta = (meta_sizing.conviction_overlay(df, spec, ppy=ppy, costs=costs)
            if th.meta_sizing else
            {"applied": False, "reason": "disabled",
             "note": "Overlay de convicción desactivado en la configuración."})

    mc = robustness.monte_carlo_simulation(
        [t["pnl_pct"] for t in full["trades"]], n_sims=th.mc_sims, seed=seed
    )
    mc_p5 = mc.get("return_pct", {}).get("p5")

    checks = {
        "min_trades": n_trades >= th.min_trades,
        "no_lookahead": not lookahead["is_leaky"],
        "wf_efficiency": wf["efficiency"] >= th.min_wf_efficiency,
        "pbo": pbo.get("pbo") is not None and pbo["pbo"] <= th.max_pbo,
        "mc_p5_positive": mc_p5 is not None and mc_p5 > th.min_mc_p5_pct,
    }

    return {
        "passed": all(checks.values()),
        "checks": checks,
        "metrics": {
            "n_trades": n_trades,
            "total_return_pct": full["total_return_pct"],
            "max_drawdown_pct": full["max_drawdown_pct"],
            "exposure_pct": full["exposure_pct"],
            "sharpe": round(metrics.sharpe_ratio(full["bar_returns"], ppy), 3),
            "sortino": round(metrics.sortino_ratio(full["bar_returns"], ppy), 3),
            "wf_efficiency": wf["efficiency"],
            "mean_oos_sharpe": wf["mean_oos_sharpe"],
            "pbo": pbo.get("pbo"),
            # Control de sobreajuste completo: de dónde salen los números, el
            # Sharpe deflactado por el nº real de pruebas, el N efectivo tras
            # agrupar genomas correlacionados y la curva E[max SR₀] vs N.
            # Se reporta, no bloquea: el gating sigue decidiéndose por PBO.
            "overfitting": overfitting,
            "deflated_sharpe": overfitting["deflated_sharpe"].get("dsr"),
            # Validación cruzada combinatoria purgada: el walk-forward da un
            # punto, esto da la nube de la que ese punto era una muestra.
            "cpcv": cpcv,
            "cpcv_sharpe_p5": cpcv.get("sharpe_p5"),
            "cpcv_sharpe_median": cpcv.get("sharpe_median"),
            # Cuánto dinero admite el edge antes de que su impacto lo anule.
            "capacity": capacity,
            "capacity_usd": capacity.get("capacity_usd"),
            # La magnitud del Sharpe sin su incertidumbre invita a leer como
            # sólido lo que es ruido: aquí va el intervalo y la probabilidad de
            # que el Sharpe verdadero supere cero.
            "significance": sig.annotate(full["bar_returns"], ppy),
            # Meta-etiquetado: si el tamaño de la posición puede modularse con
            # la convicción del meta-modelo, y qué aporta hacerlo (medido en el
            # tramo que ese modelo no vio al entrenar).
            "meta_sizing": meta,
            "meta_sizing_applied": meta.get("applied", False),
            "turnover": full["turnover"],
            "cost_drag_pct": full["total_commission_pct"],
            # Sangrado por financiación del perpetuo. Va aparte de la comisión
            # porque son costes de naturaleza distinta —uno escala con el nº de
            # operaciones, el otro con el tiempo en mercado— y sumarlos impide
            # saber cuál está matando la estrategia. Cero significa aquí «sin
            # histórico de funding», no «no costó nada».
            "funding_drag_pct": full.get("total_funding_pct", 0.0),
            "exit_reasons": full["exit_reasons"],
            "monte_carlo": {
                "prob_profit_pct": mc.get("prob_profit_pct"),
                "return_p5_pct": mc_p5,
                "return_p50_pct": mc.get("return_pct", {}).get("p50"),
            },
            "lookahead_leaky": lookahead["is_leaky"],
        },
    }


def holdout_performance(df_holdout, spec: dict, ppy: float = 365.0, costs: CostModel | None = None) -> dict:
    """Rendimiento de la finalista en el tramo de validación final intacto (neto de costes)."""
    bt = _segment_backtest(df_holdout, spec, costs)
    return {
        "return_pct": bt["total_return_pct"],
        "sharpe": round(metrics.sharpe_ratio(bt["bar_returns"], ppy), 3),
        "max_drawdown_pct": bt["max_drawdown_pct"],
        "n_trades": bt["total_trades"],
        "win_rate_pct": bt["win_rate_pct"],
        "turnover": bt["turnover"],
        "candles": len(df_holdout),
    }
