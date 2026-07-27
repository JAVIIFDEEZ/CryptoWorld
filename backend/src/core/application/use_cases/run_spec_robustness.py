"""
run_spec_robustness.py — Suite de robustez de un StrategySpec generado (Módulo 2).

Generaliza la suite de robustez (que hasta ahora solo cubría las 5 estrategias
con nombre vía Optuna) a cualquier StrategySpec componible producido por el
generador genético. NO reimplementa la matemática de robustez: invoca las mismas
primitivas del Módulo 1 (PBO/CSCV, Deflated Sharpe, Monte Carlo, permutación,
detector de lookahead) y el mismo constructor de informe/veredicto.

Como un spec tiene estructura fija (sus "parámetros" son ventanas/umbrales ya
fijados por el GA), el espacio de configuraciones para PBO/DSR se construye con
vecinos jitter alrededor del spec, en lugar de con trials de Optuna.

Incluye además validación multi-activo: reevalúa el spec en varios activos para
medir si el edge es consistente o específico de un símbolo (sobreajuste cruzado).

`run_spec_robustness_suite(df, spec, ...)` y `cross_asset_validation(dfs, spec)`
son puros (solo dominio). `RunSpecRobustnessUseCase` los envuelve obteniendo el
OHLCV.
"""

import logging
from dataclasses import dataclass

import numpy as np

from core.domain.services import backtest_metrics as metrics
from core.domain.services import backtest_robustness as robustness
from core.domain.services import backtest_bias as bias
from core.domain.services.backtest_report import build_robustness_report
from core.domain.services.strategy_evaluation import (
    DEFAULT_COSTS,
    _neighborhood_returns,
    holdout_performance,
    spec_permutation_test,
    walk_forward_oos,
)
from core.domain.services.strategy_spec import (
    compile_signals, describe_spec, spec_hash, spec_risk, spec_sizing, validate_spec,
)
from core.domain.services.technical_analysis_service import backtest_signals

logger = logging.getLogger(__name__)

MIN_CANDLES = 250

# Activos por defecto para la validación cruzada (líquidos y de historia larga).
DEFAULT_CROSS_ASSETS = ["BTC", "ETH", "BNB", "SOL", "ADA"]


@dataclass(frozen=True)
class SpecRobustnessConfig:
    """Presupuesto de cómputo de la suite de robustez de un spec."""
    n_neighbors: int = 16     # configuraciones vecinas para PBO/DSR
    n_perms: int = 120        # permutaciones del test
    n_sims: int = 800         # simulaciones de Monte Carlo
    wf_splits: int = 4        # tramos out-of-sample del walk-forward
    seed: int = 42


_PRESETS = {
    "fast": SpecRobustnessConfig(n_neighbors=8, n_perms=40, n_sims=300, wf_splits=3),
    "balanced": SpecRobustnessConfig(n_neighbors=16, n_perms=120, n_sims=800, wf_splits=4),
    "thorough": SpecRobustnessConfig(n_neighbors=24, n_perms=250, n_sims=1200, wf_splits=5),
}
DEFAULT_PRESET = "balanced"


def config_for_preset(preset: str) -> SpecRobustnessConfig:
    return _PRESETS.get(preset, _PRESETS[DEFAULT_PRESET])


def _json_safe(value):
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def run_spec_robustness_suite(
    df,
    spec: dict,
    interval: str = "1d",
    initial_capital: float = 10000.0,
    config: SpecRobustnessConfig | None = None,
) -> dict:
    """
    Suite completa de robustez sobre un spec ya compilable. Devuelve el mismo
    informe (score + veredicto + diagnósticos + métricas) que la suite de las 5
    estrategias, para poder mostrarlo con la misma capa visual.
    """
    cfg = config or SpecRobustnessConfig()
    if not validate_spec(spec):
        return {"error": "El spec de la estrategia no es válido."}

    ppy = metrics.annualization_factor(interval)
    rng = np.random.default_rng(cfg.seed)

    full = backtest_signals(df, compile_signals(df, spec), initial_capital,
                            costs=DEFAULT_COSTS, risk=spec_risk(spec), sizing=spec_sizing(spec))
    base_metrics = metrics.compute_metrics(full, ppy)
    observed_sharpe = metrics.sharpe_ratio(full["bar_returns"], ppy)

    # ── Vecindario (configuraciones jitter) → PBO + Deflated Sharpe ──
    neighbors = _neighborhood_returns(df, spec, cfg.n_neighbors, rng)
    if len(neighbors) >= 2:
        matrix = np.column_stack(neighbors)
        pbo = robustness.probability_of_backtest_overfitting(matrix)
        deflated_sharpe = robustness.deflated_sharpe_ratio(neighbors[0], neighbors[1:])
    else:
        pbo = {"pbo": None, "note": "Vecindario insuficiente para PBO."}
        deflated_sharpe = {"dsr": None, "note": "Vecindario insuficiente para DSR."}

    # ── Walk-forward (eficiencia OOS/IS) ──
    wf = walk_forward_oos(df, spec, cfg.wf_splits, ppy)
    wf_block = {
        "efficiency": wf["efficiency"],
        "mean_is_sharpe": wf["mean_is_sharpe"],
        "mean_oos_sharpe": wf["mean_oos_sharpe"],
        "n_splits": wf["n_folds"],
    }

    # ── Monte Carlo y permutación ──
    monte_carlo = robustness.monte_carlo_simulation(
        [t["pnl_pct"] for t in full["trades"]],
        initial_capital=initial_capital, n_sims=cfg.n_sims, seed=cfg.seed,
    )
    permutation = spec_permutation_test(df, spec, observed_sharpe, n_perms=cfg.n_perms, ppy=ppy, seed=cfg.seed)

    # ── Detector de lookahead ──
    lookahead = bias.detect_lookahead_bias(df, lambda d: compile_signals(d, spec), seed=cfg.seed)

    diagnostics = {
        "pbo": pbo,
        "deflated_sharpe": deflated_sharpe,
        "walk_forward_rolling": wf_block,
        "walk_forward_anchored": wf_block,
        "monte_carlo": monte_carlo,
        "permutation": permutation,
        "lookahead": lookahead,
        "recursive_instability": {"is_unstable": False, "max_rel_drift": 0.0},
    }
    report = build_robustness_report(diagnostics)

    return _json_safe({
        "spec": spec,
        "spec_hash": spec_hash(spec),
        "description": describe_spec(spec),
        "interval": interval,
        "robustness_score": report["robustness_score"],
        "verdict": report["verdict"],
        "explanation": report["explanation"],
        "reasons": report["reasons"],
        "strengths": report["strengths"],
        "component_scores": report["component_scores"],
        "metrics": base_metrics,
        "diagnostics": {
            "deflated_sharpe": deflated_sharpe,
            "pbo": pbo,
            "walk_forward_anchored": wf_block,
            "monte_carlo": {k: v for k, v in monte_carlo.items() if k != "return_distribution"},
            "permutation": permutation,
            "lookahead": lookahead,
        },
        "charts": {
            "equity_curve": full["equity_curve"],
            "monte_carlo_distribution": monte_carlo.get("return_distribution", []),
        },
    })


def cross_asset_validation(
    dfs: dict,
    spec: dict,
    interval: str = "1d",
    wf_splits: int = 4,
) -> dict:
    """
    Reevalúa el spec en varios activos (puro: recibe los DataFrames ya cargados).
    Devuelve por activo el Sharpe OOS y el retorno, y un 'consistency_score' =
    fracción de activos con Sharpe OOS positivo. Un edge robusto generaliza a
    otros símbolos; uno sobreajustado solo funciona en el activo de origen.
    """
    ppy = metrics.annualization_factor(interval)
    rows = []
    positives = 0
    for symbol, df in dfs.items():
        if df is None or len(df) < MIN_CANDLES:
            rows.append({"symbol": symbol, "ok": False, "note": "Datos insuficientes"})
            continue
        full = backtest_signals(df, compile_signals(df, spec))
        wf = walk_forward_oos(df, spec, wf_splits, ppy)
        oos = wf["mean_oos_sharpe"]
        if oos > 0:
            positives += 1
        rows.append({
            "symbol": symbol,
            "ok": True,
            "oos_sharpe": oos,
            "sharpe": round(metrics.sharpe_ratio(full["bar_returns"], ppy), 3),
            "total_return_pct": full["total_return_pct"],
            "max_drawdown_pct": full["max_drawdown_pct"],
            "n_trades": full["total_trades"],
        })
    evaluated = [r for r in rows if r.get("ok")]
    consistency = (positives / len(evaluated)) if evaluated else 0.0
    return _json_safe({
        "n_assets": len(evaluated),
        "n_positive_oos": positives,
        "consistency_score": round(consistency, 3),
        "results": sorted(rows, key=lambda r: r.get("oos_sharpe", -99), reverse=True),
    })


class RunSpecRobustnessUseCase:
    """Carga el OHLCV (activo principal + cesta cruzada) y ejecuta la suite."""

    def execute(
        self,
        spec: dict,
        asset_symbol: str,
        interval: str = "1d",
        limit: int = 365,
        initial_capital: float = 10000.0,
        preset: str = DEFAULT_PRESET,
        cross_assets: list | None = None,
    ) -> dict:
        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
        from django.core.cache import cache
        from core.domain.services.strategy_spec import spec_hash

        symbol = asset_symbol.upper()

        # La suite es determinista para (spec, activo, marco, preset): cachear
        # evita recomputar cientos de backtests si se reabre el mismo análisis.
        cache_key = f"spec_robust:{spec_hash(spec)}:{symbol}:{interval}:{preset}"
        cached = cache.get(cache_key)
        if cached is not None:
            return {**cached, "cached": True}

        main = fetch_ohlcv_dataframe(symbol=symbol, interval=interval, limit=limit)
        if main is None or main.df.empty or len(main.df) < MIN_CANDLES:
            return {"error": f"Datos insuficientes para {symbol} (se necesitan ≥{MIN_CANDLES} velas)."}

        cfg = config_for_preset(preset)
        report = run_spec_robustness_suite(
            main.df, spec, interval=interval, initial_capital=initial_capital, config=cfg,
        )
        if "error" in report:
            return report
        report["asset_symbol"] = symbol
        report["data_source"] = main.source
        report["candles_count"] = len(main.df)
        report["preset"] = preset

        # ── Validación multi-activo (excluye el activo principal) ──
        basket = [s.upper() for s in (cross_assets or DEFAULT_CROSS_ASSETS) if s.upper() != symbol][:5]
        dfs = {}
        for s in basket:
            res = fetch_ohlcv_dataframe(symbol=s, interval=interval, limit=limit)
            dfs[s] = res.df if (res and not res.df.empty) else None
        report["cross_asset"] = cross_asset_validation(dfs, spec, interval, cfg.wf_splits)

        logger.info(
            "spec_robustness %s [%s] → %s (%d/100), consistencia cruzada %.0f%%",
            symbol, preset, report.get("verdict"), report.get("robustness_score", 0),
            report["cross_asset"]["consistency_score"] * 100,
        )
        cache.set(cache_key, report, 3600)  # 1 hora, alineado con la suite clásica
        return report
