"""
backtest_robustness.py — Diagnósticos de robustez / sobreajuste de estrategias.

Capa de dominio (Python puro, sin framework): recibe DataFrames OHLCV y la
salida del motor de backtest, y produce los diagnósticos que detectan si una
estrategia está sobreajustada:

  - optimize_parameters:        Optuna sobre el espacio de parámetros (guarda
                                la matriz de trials para PBO/DSR).
  - walk_forward_analysis:      optimiza in-sample, evalúa out-of-sample
                                (ventanas rolling y anchored) y mide la
                                eficiencia walk-forward (OOS/IS).
  - monte_carlo_simulation:     bootstrap del orden de trades → distribución
                                de retorno y drawdown con percentiles.
  - permutation_test:           ¿el edge es significativo o suerte?
  - deflated_sharpe_ratio:      Sharpe corregido por nº de trials, skew y kurt.
  - probability_of_backtest_overfitting (PBO): CSCV sobre la matriz de trials.

Determinista: todas las fuentes de aleatoriedad reciben semilla.
"""

from itertools import combinations

import numpy as np
import optuna
from scipy.stats import kurtosis, norm, skew

from core.domain.services import backtest_metrics as m
from core.domain.services.technical_analysis_service import (
    run_backtest_full,
    strategy_param_space,
)

optuna.logging.set_verbosity(optuna.logging.WARNING)

_EULER_MASCHERONI = 0.5772156649015329


# ═══════════════════════════════════════════════════════════════════
# Optimización de parámetros (Optuna) — guarda la matriz de trials
# ═══════════════════════════════════════════════════════════════════

def _suggest_params(trial: "optuna.Trial", param_space: list[dict]) -> dict:
    params = {}
    for p in param_space:
        if p["type"] == "int":
            params[p["name"]] = trial.suggest_int(p["name"], p["low"], p["high"])
        else:
            params[p["name"]] = trial.suggest_float(p["name"], p["low"], p["high"])
    return params


def _objective_value(bt: dict, objective: str, ppy: float) -> float:
    if objective == "sortino":
        return m.sortino_ratio(bt["bar_returns"], ppy)
    if objective == "calmar":
        return m.calmar_ratio(bt["equity_curve"], ppy)
    if objective == "total_return":
        return float(bt["total_return_pct"])
    return m.sharpe_ratio(bt["bar_returns"], ppy)  # default: Sharpe


def optimize_parameters(
    df,
    strategy: str,
    n_trials: int = 40,
    objective: str = "sharpe",
    periods_per_year: float = 365.0,
    seed: int = 42,
) -> dict:
    """
    Busca los mejores parámetros con Optuna (TPE, semilla fija) y devuelve la
    matriz de trials (params, valor objetivo y retornos por vela de cada uno),
    imprescindible para PBO y DSR.
    """
    space = strategy_param_space(strategy)

    def objective_fn(trial: "optuna.Trial") -> float:
        params = _suggest_params(trial, space)
        bt = run_backtest_full(df, strategy, params=params)
        if "error" in bt:
            return -1e9
        trial.set_user_attr("params", params)
        trial.set_user_attr("bar_returns", bt["bar_returns"])
        return _objective_value(bt, objective, periods_per_year)

    study = optuna.create_study(
        direction="maximize", sampler=optuna.samplers.TPESampler(seed=seed)
    )
    study.optimize(objective_fn, n_trials=n_trials, show_progress_bar=False)

    trials = [
        {
            "params": t.user_attrs.get("params", {}),
            "value": float(t.value),
            "bar_returns": t.user_attrs.get("bar_returns", []),
        }
        for t in study.trials
        if t.value is not None and t.value > -1e8
    ]
    # Ranking de trials por valor objetivo (para graficar)
    ranking = sorted(
        ({"params": t["params"], "value": round(t["value"], 4)} for t in trials),
        key=lambda x: x["value"],
        reverse=True,
    )
    return {
        "best_params": study.best_params,
        "best_value": round(float(study.best_value), 4),
        "objective": objective,
        "n_trials": len(trials),
        "trials": trials,            # incluye bar_returns (uso interno PBO/DSR)
        "ranking": ranking[:15],     # top configuraciones (uso en la UI)
    }


# ═══════════════════════════════════════════════════════════════════
# Walk-forward analysis (rolling + anchored)
# ═══════════════════════════════════════════════════════════════════

def walk_forward_analysis(
    df,
    strategy: str,
    n_splits: int = 4,
    anchored: bool = False,
    n_trials: int = 20,
    objective: str = "sharpe",
    periods_per_year: float = 365.0,
    seed: int = 42,
    min_window: int = 60,
) -> dict:
    """
    Divide la serie en n_splits tramos OOS consecutivos. Para cada tramo
    optimiza los parámetros en el histórico previo (anchored: desde el inicio;
    rolling: una ventana móvil) y los evalúa fuera de muestra. Reporta el
    Sharpe IS/OOS por fold y la eficiencia walk-forward (OOS/IS).
    """
    n = len(df)
    fold = n // (n_splits + 1)
    folds = []
    is_sharpes: list[float] = []
    oos_sharpes: list[float] = []
    oos_returns: list[float] = []

    if fold < 30:
        return {
            "mode": "anchored" if anchored else "rolling",
            "n_splits": 0,
            "folds": [],
            "efficiency": None,
            "mean_is_sharpe": None,
            "mean_oos_sharpe": None,
            "note": "Histórico insuficiente para walk-forward.",
        }

    for k in range(1, n_splits + 1):
        test_start = k * fold
        test_end = n if k == n_splits else (k + 1) * fold
        if anchored:
            train_df = df.iloc[:test_start]
        else:
            train_df = df.iloc[max(0, test_start - 2 * fold):test_start]
        test_df = df.iloc[test_start:test_end]
        if len(train_df) < min_window or len(test_df) < 30:
            continue

        opt = optimize_parameters(
            train_df, strategy, n_trials=n_trials, objective=objective,
            periods_per_year=periods_per_year, seed=seed,
        )
        best = opt["best_params"]
        is_bt = run_backtest_full(train_df, strategy, params=best)
        oos_bt = run_backtest_full(test_df, strategy, params=best)
        is_s = m.sharpe_ratio(is_bt["bar_returns"], periods_per_year)
        oos_s = m.sharpe_ratio(oos_bt["bar_returns"], periods_per_year)

        is_sharpes.append(is_s)
        oos_sharpes.append(oos_s)
        oos_returns.append(oos_bt["total_return_pct"])
        folds.append({
            "fold": k,
            "best_params": best,
            "is_sharpe": round(is_s, 3),
            "oos_sharpe": round(oos_s, 3),
            "oos_return_pct": oos_bt["total_return_pct"],
            "oos_equity": [round(float(x), 2) for x in oos_bt["equity_curve"]],
        })

    mean_is = float(np.mean(is_sharpes)) if is_sharpes else 0.0
    mean_oos = float(np.mean(oos_sharpes)) if oos_sharpes else 0.0
    efficiency = (mean_oos / mean_is) if mean_is > 1e-9 else 0.0

    return {
        "mode": "anchored" if anchored else "rolling",
        "n_splits": len(folds),
        "folds": folds,
        "mean_is_sharpe": round(mean_is, 3),
        "mean_oos_sharpe": round(mean_oos, 3),
        "efficiency": round(float(efficiency), 3),
        "oos_return_mean_pct": round(float(np.mean(oos_returns)), 2) if oos_returns else 0.0,
    }


# ═══════════════════════════════════════════════════════════════════
# Monte Carlo (bootstrap del orden de trades)
# ═══════════════════════════════════════════════════════════════════

def _equity_max_dd(equity: np.ndarray) -> float:
    peak = equity[0]
    mdd = 0.0
    for v in equity:
        if v > peak:
            peak = v
        if peak > 0:
            dd = (peak - v) / peak * 100
            if dd > mdd:
                mdd = dd
    return float(mdd)


def monte_carlo_simulation(
    trade_pnls,
    initial_capital: float = 10000.0,
    n_sims: int = 1000,
    seed: int = 42,
) -> dict:
    """
    Resamplea con reemplazo el orden y composición de las operaciones para
    estimar la distribución del resultado: percentiles 5/50/95 del retorno y
    del max drawdown, y probabilidad de terminar en beneficio.
    """
    pnls = np.asarray(trade_pnls, dtype=float) / 100.0
    if pnls.size < 2:
        return {
            "n_sims": 0,
            "return_pct": {"p5": None, "p50": None, "p95": None},
            "max_drawdown_pct": {"p5": None, "p50": None, "p95": None},
            "prob_profit_pct": None,
            "return_distribution": [],
            "note": "Operaciones insuficientes para Monte Carlo.",
        }

    rng = np.random.default_rng(seed)
    final_returns = np.empty(n_sims)
    max_dds = np.empty(n_sims)
    for s in range(n_sims):
        sample = rng.choice(pnls, size=pnls.size, replace=True)
        equity = np.concatenate([[initial_capital], initial_capital * np.cumprod(1 + sample)])
        final_returns[s] = (equity[-1] / initial_capital - 1) * 100
        max_dds[s] = _equity_max_dd(equity)

    return {
        "n_sims": n_sims,
        "return_pct": {
            "p5": round(float(np.percentile(final_returns, 5)), 2),
            "p50": round(float(np.percentile(final_returns, 50)), 2),
            "p95": round(float(np.percentile(final_returns, 95)), 2),
        },
        "max_drawdown_pct": {
            "p5": round(float(np.percentile(max_dds, 5)), 2),
            "p50": round(float(np.percentile(max_dds, 50)), 2),
            "p95": round(float(np.percentile(max_dds, 95)), 2),
        },
        "prob_profit_pct": round(float((final_returns > 0).mean() * 100), 2),
        "return_distribution": [round(float(x), 3) for x in final_returns],
    }


# ═══════════════════════════════════════════════════════════════════
# Permutation test sobre la serie de precios
# ═══════════════════════════════════════════════════════════════════

def permutation_test(
    df,
    strategy: str,
    params: dict,
    observed_sharpe: float,
    n_perms: int = 200,
    periods_per_year: float = 365.0,
    seed: int = 42,
) -> dict:
    """
    Permuta los retornos de la serie de precios (destruye la estructura
    temporal) y re-ejecuta la estrategia. Si el edge es real, el Sharpe
    observado debe superar al de la mayoría de permutaciones (p-valor bajo).
    """
    close = df["close"].values.astype(float)
    if close.size < 30 or np.any(close <= 0):
        return {"p_value": None, "observed_sharpe": round(observed_sharpe, 3),
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
        bt = run_backtest_full(pdf, strategy, params=params)
        s = m.sharpe_ratio(bt["bar_returns"], periods_per_year) if "error" not in bt else 0.0
        if s >= observed_sharpe:
            count_ge += 1

    p_value = (count_ge + 1) / (n_perms + 1)
    return {
        "p_value": round(float(p_value), 4),
        "observed_sharpe": round(float(observed_sharpe), 3),
        "n_perms": n_perms,
        "significant": bool(p_value < 0.05),
    }


# ═══════════════════════════════════════════════════════════════════
# Deflated Sharpe Ratio (Bailey & López de Prado)
# ═══════════════════════════════════════════════════════════════════

def _per_period_sharpe(returns) -> float:
    r = np.asarray(returns, dtype=float)
    if r.size < 2:
        return 0.0
    sd = r.std(ddof=1)
    return float(r.mean() / sd) if sd > 0 else 0.0


def deflated_sharpe_ratio(returns, trial_returns_list) -> dict:
    """
    DSR: probabilidad de que el Sharpe observado sea real una vez corregido
    por el nº de configuraciones probadas y la no-normalidad (skew/kurtosis)
    de los retornos. DSR alto (→1) = fiable; bajo (→0) = probable sobreajuste.
    """
    r = np.asarray(returns, dtype=float)
    T = r.size
    if T < 4:
        return {"dsr": None, "note": "Serie demasiado corta para DSR."}

    sr_hat = _per_period_sharpe(r)
    sk = float(skew(r))
    ku = float(kurtosis(r, fisher=False))  # kurtosis total (3 si normal)

    trial_sr = np.array([
        _per_period_sharpe(tr) for tr in trial_returns_list if len(tr) >= 2
    ])
    n_trials = max(int(trial_sr.size), 1)
    var_sr = float(trial_sr.var(ddof=1)) if trial_sr.size > 1 else 0.0

    if n_trials > 1 and var_sr > 0:
        z1 = norm.ppf(1 - 1.0 / n_trials)
        z2 = norm.ppf(1 - 1.0 / (n_trials * np.e))
        sr0 = np.sqrt(var_sr) * ((1 - _EULER_MASCHERONI) * z1 + _EULER_MASCHERONI * z2)
    else:
        sr0 = 0.0

    denom = 1 - sk * sr_hat + ((ku - 1) / 4.0) * sr_hat ** 2
    if denom <= 0:
        dsr = 0.0
    else:
        dsr = float(norm.cdf((sr_hat - sr0) * np.sqrt(T - 1) / np.sqrt(denom)))

    return {
        "dsr": round(dsr, 4),
        "sr_per_period": round(sr_hat, 4),
        "sr0_threshold": round(float(sr0), 4),
        "n_trials": n_trials,
        "skew": round(sk, 3),
        "kurtosis": round(ku, 3),
    }


# ═══════════════════════════════════════════════════════════════════
# Probability of Backtest Overfitting (PBO) vía CSCV
# ═══════════════════════════════════════════════════════════════════

def _partition_sharpe(submatrix: np.ndarray) -> np.ndarray:
    """Sharpe por configuración (columna) sobre un subconjunto de filas."""
    mu = submatrix.mean(axis=0)
    sd = submatrix.std(axis=0, ddof=1)
    return np.divide(mu, sd, out=np.zeros_like(mu), where=sd > 0)


def probability_of_backtest_overfitting(
    returns_matrix, n_partitions: int = 10
) -> dict:
    """
    CSCV (Bailey et al. 2014): parte la serie en S bloques, prueba todas las
    combinaciones de S/2 bloques in-sample vs el resto out-of-sample, elige la
    mejor configuración IS y mira su rango OOS. PBO = fracción de splits donde
    la mejor IS queda por debajo de la mediana OOS (logit ≤ 0). Alto = sobreajuste.
    """
    M = np.asarray(returns_matrix, dtype=float)
    if M.ndim != 2 or M.shape[1] < 2:
        return {"pbo": None, "note": "Se requieren ≥2 configuraciones para PBO."}

    T, N = M.shape
    S = n_partitions - (n_partitions % 2)  # par
    if S < 2 or T < S:
        return {"pbo": None, "note": "Datos insuficientes para CSCV."}

    blocks = np.array_split(np.arange(T), S)
    logits = []
    for is_combo in combinations(range(S), S // 2):
        is_set = set(is_combo)
        is_rows = np.concatenate([blocks[i] for i in is_combo])
        oos_rows = np.concatenate([blocks[i] for i in range(S) if i not in is_set])

        is_perf = _partition_sharpe(M[is_rows])
        oos_perf = _partition_sharpe(M[oos_rows])

        n_star = int(np.argmax(is_perf))                  # mejor configuración IS
        # rango relativo OOS de esa configuración (0 = peor, 1 = mejor)
        rank = float((oos_perf < oos_perf[n_star]).sum()) / max(N - 1, 1)
        omega = min(max(rank, 1e-6), 1 - 1e-6)
        logits.append(float(np.log(omega / (1 - omega))))

    logits_arr = np.array(logits)
    pbo = float((logits_arr <= 0).mean())
    return {
        "pbo": round(pbo, 4),
        "n_partitions": S,
        "n_combinations": len(logits),
        "n_configs": N,
    }
