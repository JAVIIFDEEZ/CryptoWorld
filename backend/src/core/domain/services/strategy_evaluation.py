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
    """
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
            "turnover": full["turnover"],
            "cost_drag_pct": full["total_commission_pct"],
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
