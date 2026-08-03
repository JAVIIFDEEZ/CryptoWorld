"""
run_robust_backtest.py — Caso de uso: Suite de robustez de backtest.

Orquesta todos los diagnósticos de la capa de dominio (métricas, walk-forward,
Optuna, Monte Carlo, permutation test, DSR, PBO y los dos detectores de sesgo)
y produce el informe con el Robustness Score y el veredicto.

`run_robustness_suite(df, ...)` es puro (solo dominio) y testeable sin red ni
Celery. La clase `RunRobustBacktestUseCase` lo envuelve obteniendo el OHLCV
con la cadena compartida Binance → KuCoin → CoinGecko.
"""

import logging
from dataclasses import dataclass, replace

import numpy as np

from core.domain.services import backtest_metrics as metrics
from core.domain.services import backtest_robustness as robustness
from core.domain.services import backtest_bias as bias
from core.domain.services import significance
from core.domain.services.backtest_execution import CostModel
from core.domain.services.backtest_report import build_robustness_report
from core.domain.services.technical_analysis_service import (
    STRATEGIES,
    generate_signals,
    run_backtest_full,
    strategy_indicator_series,
)

logger = logging.getLogger(__name__)

# Velas mínimas: el walk-forward necesita varios tramos IS/OOS con tamaño suficiente.
MIN_CANDLES = 250


@dataclass(frozen=True)
class RobustnessConfig:
    """Presupuesto de cómputo de la suite (los tests usan valores pequeños)."""
    n_trials: int = 40          # trials de Optuna (in-sample, para PBO/DSR)
    wf_splits: int = 4          # tramos out-of-sample del walk-forward
    wf_trials: int = 20         # trials de optimización por fold
    n_perms: int = 150          # permutaciones del permutation test
    n_sims: int = 1000          # simulaciones de Monte Carlo
    objective: str = "sharpe"   # objetivo de optimización
    seed: int = 42
    # Costes de ejecución aplicados a TODA la suite. Antes corría en bruto: las
    # métricas y el veredicto salían de una simulación en la que operar era
    # gratis, y la optimización premiaba rotaciones que en real sangran. Los
    # mismos valores por defecto que usa el generador de estrategias.
    commission_bps: float = 10.0
    slippage_bps: float = 5.0
    # System Parameter Permutation: nº máximo de combinaciones de la rejilla.
    # 0 lo desactiva (los presets rápidos no lo pagan).
    spp_max_combos: int = 120


# Presets de cómputo: rapidez vs exhaustividad. El usuario elige según
# cuánto quiera esperar (la suite son cientos de backtests).
_PRESETS = {
    "fast": RobustnessConfig(n_trials=12, wf_splits=2, wf_trials=6, n_perms=30, n_sims=300),
    "balanced": RobustnessConfig(n_trials=25, wf_splits=3, wf_trials=12, n_perms=80, n_sims=600),
    "thorough": RobustnessConfig(n_trials=40, wf_splits=4, wf_trials=20, n_perms=150, n_sims=1000),
}
DEFAULT_PRESET = "balanced"

# La suite es determinista (semillas fijas); cachear su resultado evita
# recomputar cientos de backtests en cada clic. TTL alineado con los datos.
_CACHE_TTL = 3600  # 1 hora


def config_for_preset(preset: str, objective: str = "sharpe") -> RobustnessConfig:
    """Config de cómputo del preset, con el objetivo de optimización elegido."""
    base = _PRESETS.get(preset, _PRESETS[DEFAULT_PRESET])
    return replace(base, objective=objective)



def _stitch_oos_equity(folds: list[dict], initial_capital: float) -> list[float]:
    """Encadena las curvas OOS de cada fold en una sola serie continua."""
    equity = [round(initial_capital, 2)]
    capital = initial_capital
    for fold in folds:
        seg = fold.get("oos_equity", [])
        if len(seg) < 2 or seg[0] in (0, None):
            continue
        base = seg[0]
        for point in seg[1:]:
            capital *= point / base
            base = point
            equity.append(round(capital, 2))
    return equity


def _json_safe(value):
    """Sustituye inf/nan por None recursivamente: el payload pasa por JSON
    (DRF/Celery-Redis) y los floats no finitos no son JSON-compliant."""
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


def run_robustness_suite(
    df,
    strategy: str,
    interval: str = "1d",
    initial_capital: float = 10000.0,
    config: RobustnessConfig | None = None,
) -> dict:
    """
    Ejecuta la suite completa sobre un DataFrame OHLCV ya cargado.
    Devuelve el informe (métricas + diagnósticos + veredicto + series).
    """
    cfg = config or RobustnessConfig()
    if strategy not in STRATEGIES:
        raise ValueError(f"Estrategia '{strategy}' no reconocida.")

    ppy = metrics.annualization_factor(interval)

    # Costes de ejecución aplicados a TODA la suite (optimización, walk-forward,
    # permutación y backtest final). Sin esto, el titular de la suite era el
    # rendimiento de un mundo donde operar es gratis.
    costs = CostModel(commission_bps=cfg.commission_bps, slippage_bps=cfg.slippage_bps)

    # ── Optimización in-sample sobre toda la serie (base de PBO y DSR) ──
    optimization = robustness.optimize_parameters(
        df, strategy, n_trials=cfg.n_trials, objective=cfg.objective,
        periods_per_year=ppy, seed=cfg.seed, costs=costs,
    )
    best_params = optimization["best_params"]
    trials = optimization["trials"]

    # Backtest con los mejores parámetros (estrategia evaluada)
    best_bt = run_backtest_full(df, strategy, initial_capital, best_params, costs=costs)
    base_metrics = metrics.compute_metrics(best_bt, ppy)
    observed_sharpe = metrics.sharpe_ratio(best_bt["bar_returns"], ppy)

    # ── DSR y PBO sobre la matriz de trials ──
    trial_returns = [t["bar_returns"] for t in trials]
    deflated_sharpe = robustness.deflated_sharpe_ratio(best_bt["bar_returns"], trial_returns)
    if len(trials) >= 2:
        returns_matrix = np.column_stack([t["bar_returns"] for t in trials])
        pbo = robustness.probability_of_backtest_overfitting(returns_matrix)
    else:
        pbo = {"pbo": None, "note": "Trials insuficientes para PBO."}

    # ── Walk-forward (rolling + anchored) ──
    wf_rolling = robustness.walk_forward_analysis(
        df, strategy, n_splits=cfg.wf_splits, anchored=False,
        n_trials=cfg.wf_trials, objective=cfg.objective,
        periods_per_year=ppy, seed=cfg.seed, costs=costs,
    )
    wf_anchored = robustness.walk_forward_analysis(
        df, strategy, n_splits=cfg.wf_splits, anchored=True,
        n_trials=cfg.wf_trials, objective=cfg.objective,
        periods_per_year=ppy, seed=cfg.seed, costs=costs,
    )

    # ── Monte Carlo y permutation test ──
    monte_carlo = robustness.monte_carlo_simulation(
        [t["pnl_pct"] for t in best_bt["trades"]],
        initial_capital=initial_capital, n_sims=cfg.n_sims, seed=cfg.seed,
    )
    permutation = robustness.permutation_test(
        df, strategy, best_params, observed_sharpe,
        n_perms=cfg.n_perms, periods_per_year=ppy, seed=cfg.seed, costs=costs,
    )

    # ── System Parameter Permutation ──
    # La mediana de todo el espacio de parámetros es la estimación que nadie
    # eligió por buena; la brecha con el mejor mide cuánto del resultado venía
    # de haber acertado la configuración.
    spp = robustness.system_parameter_permutation(
        df, strategy, ppy=ppy, costs=costs, max_combos=cfg.spp_max_combos,
    ) if cfg.spp_max_combos > 0 else {"n_combos": 0, "note": "SPP desactivado en este preset."}

    # ── Detectores de sesgo ──
    lookahead = bias.detect_lookahead_bias(
        df, lambda d: generate_signals(d, strategy, best_params), seed=cfg.seed,
    )
    recursive_instability = bias.detect_recursive_instability(
        df, lambda d: strategy_indicator_series(d, strategy, best_params),
    )

    diagnostics = {
        "pbo": pbo,
        "deflated_sharpe": deflated_sharpe,
        "walk_forward_rolling": wf_rolling,
        "walk_forward_anchored": wf_anchored,
        "monte_carlo": monte_carlo,
        "permutation": permutation,
        "lookahead": lookahead,
        "recursive_instability": recursive_instability,
    }
    report = build_robustness_report(diagnostics)

    # ── Series para graficar ──
    charts = {
        "oos_equity_curve": _stitch_oos_equity(wf_anchored.get("folds", []), initial_capital),
        "monte_carlo_distribution": monte_carlo.get("return_distribution", []),
        "trial_ranking": optimization.get("ranking", []),
    }

    # Quitar bar_returns de la matriz de trials del payload (uso interno, pesado)
    optimization_public = {
        k: v for k, v in optimization.items() if k != "trials"
    }

    return _json_safe({
        "strategy": strategy,
        "strategy_name": STRATEGIES[strategy]["name"],
        "interval": interval,
        "best_params": best_params,
        "robustness_score": report["robustness_score"],
        "verdict": report["verdict"],
        "explanation": report["explanation"],
        "reasons": report["reasons"],
        "strengths": report["strengths"],
        "component_scores": report["component_scores"],
        "metrics": base_metrics,
        # ── Titular honesto ───────────────────────────────────────
        # `metrics` es rendimiento IN-SAMPLE: los parámetros se eligieron sobre
        # esa misma serie, así que su Sharpe es la cota superior optimista, no
        # una expectativa. El titular que debe leerse primero es el de fuera de
        # muestra y deflactado por el nº de configuraciones probadas.
        "headline": {
            # Magnitud e incertidumbre juntas: el intervalo dice si el Sharpe
            # es distinguible de cero con este histórico, y el PSR con qué
            # probabilidad. Separarlos en dos sitios es cómo se acaba mostrando
            # solo la magnitud.
            "significance": significance.annotate(best_bt["bar_returns"], ppy),
            "oos_sharpe": wf_anchored.get("mean_oos_sharpe"),
            "in_sample_sharpe": round(float(observed_sharpe), 3),
            "deflated_sharpe": deflated_sharpe.get("dsr"),
            "n_trials": deflated_sharpe.get("n_trials"),
            "expected_max_sharpe_by_chance": deflated_sharpe.get("sr0_threshold"),
            "walk_forward_efficiency": wf_anchored.get("efficiency"),
            "costs_applied": True,
            "commission_bps": cfg.commission_bps,
            "slippage_bps": cfg.slippage_bps,
            "note": (
                "El Sharpe fuera de muestra es la cifra a mirar. El in-sample "
                f"({observed_sharpe:.2f}) sale de optimizar sobre esa misma serie y "
                "siempre es optimista. Todas las cifras son NETAS de costes "
                f"({cfg.commission_bps:.0f}+{cfg.slippage_bps:.0f} bps por lado) y el "
                "Sharpe deflactado corrige por las "
                f"{deflated_sharpe.get('n_trials', 0)} configuraciones probadas."
            ),
        },
        "disclaimer": (
            "Resultados SIMULADOS sobre datos históricos. Una simulación no es "
            "una previsión: el rendimiento pasado no garantiza el futuro y esta "
            "información no constituye asesoramiento financiero."
        ),
        "diagnostics": {
            "deflated_sharpe": deflated_sharpe,
            "pbo": pbo,
            "walk_forward_rolling": {k: v for k, v in wf_rolling.items() if k != "folds"},
            "walk_forward_anchored": {
                "mode": wf_anchored.get("mode"),
                "n_splits": wf_anchored.get("n_splits"),
                "efficiency": wf_anchored.get("efficiency"),
                "mean_is_sharpe": wf_anchored.get("mean_is_sharpe"),
                "mean_oos_sharpe": wf_anchored.get("mean_oos_sharpe"),
                "folds": [
                    {k: v for k, v in f.items() if k != "oos_equity"}
                    for f in wf_anchored.get("folds", [])
                ],
            },
            "monte_carlo": {k: v for k, v in monte_carlo.items() if k != "return_distribution"},
            "permutation": permutation,
            "lookahead": lookahead,
            "recursive_instability": recursive_instability,
            "system_parameter_permutation": spp,
        },
        "optimization": optimization_public,
        "charts": charts,
    })


class RunRobustBacktestUseCase:
    """Carga el OHLCV y ejecuta la suite de robustez, con caché de 1 hora."""

    def execute(
        self,
        asset_symbol: str,
        strategy: str,
        interval: str = "1d",
        limit: int = 365,
        initial_capital: float = 10000.0,
        objective: str = "sharpe",
        preset: str = DEFAULT_PRESET,
        config: RobustnessConfig | None = None,
    ) -> dict:
        # Import diferido: mantiene run_robustness_suite (dominio puro)
        # importable sin arrastrar la infraestructura/Django.
        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
        from django.core.cache import cache

        symbol = asset_symbol.upper()

        if strategy not in STRATEGIES:
            return {
                "error": f"Estrategia '{strategy}' no reconocida.",
                "available_strategies": list(STRATEGIES.keys()),
            }

        cache_key = f"robust_bt:{symbol}:{strategy}:{interval}:{objective}:{preset}"
        cached = cache.get(cache_key)
        if cached is not None:
            return {**cached, "cached": True}

        result = fetch_ohlcv_dataframe(symbol=symbol, interval=interval, limit=limit)
        if result is None or result.df.empty or len(result.df) < MIN_CANDLES:
            return {
                "error": (
                    f"Se necesitan al menos {MIN_CANDLES} velas para la suite de "
                    f"robustez y no hay suficientes datos para {symbol}."
                ),
            }

        cfg = config or config_for_preset(preset, objective)
        report = run_robustness_suite(
            result.df, strategy, interval=interval,
            initial_capital=initial_capital, config=cfg,
        )
        report["asset_symbol"] = symbol
        report["data_source"] = result.source
        report["candles_count"] = len(result.df)
        report["preset"] = preset
        cache.set(cache_key, report, _CACHE_TTL)
        logger.info(
            "Suite de robustez %s/%s [%s] → %s (%d/100)",
            symbol, strategy, preset, report.get("verdict"), report.get("robustness_score", 0),
        )
        return report


class CompareStrategiesUseCase:
    """
    Ejecuta la suite de robustez para las 5 estrategias y devuelve un ranking
    por Robustness Score. Reutiliza la caché por estrategia, así que repetir
    la comparación es prácticamente instantáneo.
    """

    def execute(
        self,
        asset_symbol: str,
        interval: str = "1d",
        objective: str = "sharpe",
        preset: str = "fast",
    ) -> dict:
        symbol = asset_symbol.upper()
        runner = RunRobustBacktestUseCase()
        rows = []
        for strat in STRATEGIES:
            rep = runner.execute(
                asset_symbol=symbol, strategy=strat, interval=interval,
                objective=objective, preset=preset,
            )
            if "error" in rep:
                rows.append({"strategy": strat, "strategy_name": STRATEGIES[strat]["name"], "error": rep["error"]})
                continue
            rows.append({
                "strategy": strat,
                "strategy_name": rep["strategy_name"],
                "robustness_score": rep["robustness_score"],
                "verdict": rep["verdict"],
                "best_params": rep["best_params"],
                "sharpe": rep["metrics"]["sharpe"],
                "max_drawdown_pct": rep["metrics"]["max_drawdown_pct"],
                "pbo": rep["diagnostics"]["pbo"].get("pbo"),
                "dsr": rep["diagnostics"]["deflated_sharpe"].get("dsr"),
                "oos_efficiency": rep["diagnostics"]["walk_forward_anchored"].get("efficiency"),
            })

        scored = [r for r in rows if "error" not in r]
        failed = [r for r in rows if "error" in r]
        scored.sort(key=lambda r: r["robustness_score"], reverse=True)

        if not scored:
            return {
                "error": "Ninguna estrategia pudo evaluarse.",
                "details": failed,
                "asset_symbol": symbol,
            }

        return {
            "asset_symbol": symbol,
            "interval": interval,
            "objective": objective,
            "preset": preset,
            "ranking": scored + failed,
            "best": scored[0],
        }
