"""
compare_strategies.py — Comparador cara a cara de estrategias guardadas.

La decisión real de un desk no es "¿es buena esta estrategia?" sino "¿a CUÁL le
asigno capital?". Este caso de uso pone 2-4 estrategias lado a lado:

  · Evidencia ALMACENADA de cada una (fitness, Sharpe OOS, PBO, eficiencia WF,
    holdout, multi-activo): lo que demostraron al aprobarse.
  · Re-ejecución FRESCA sobre datos actuales: equity normalizada (crecimiento
    de 1€, comparable entre activos y marcos), retorno de la ventana, y un
    walk-forward actual (¿quién envejece mejor?).
  · CORRELACIÓN entre sus retornos diarios: dos rentables correlacionadas son
    el mismo edge — la pareja más diversificadora vale más que la más rentable.
  · Veredictos por dimensión (no un ganador único: cada dimensión responde a
    una pregunta distinta).

Reutiliza run_strategy_on_recent (cartera de campeonas) y las primitivas de
portfolio_analysis; no reimplementa matemáticas.
"""

import logging

import numpy as np

logger = logging.getLogger(__name__)

MIN_IDS = 2
MAX_IDS = 4
_EQUITY_POINTS = 160


def _downsample(values: list, points: int = _EQUITY_POINTS) -> list:
    arr = np.asarray(values, dtype=float)
    if arr.size > points:
        idx = np.linspace(0, arr.size - 1, points).astype(int)
        arr = arr[idx]
    return [round(float(v), 5) for v in arr]


class CompareStrategiesUseCase:

    def execute(self, ids: list[int]) -> dict:
        from core.application.use_cases.strategy_portfolio import run_strategy_on_recent
        from core.domain.services import backtest_metrics as metrics
        from core.domain.services.portfolio_analysis import (
            align_returns, correlation_matrix,
        )
        from core.domain.services.strategy_evaluation import walk_forward_oos
        from core.domain.services.strategy_spec import describe_spec
        from core.infrastructure.persistence.models import StrategyDefinition

        ids = list(dict.fromkeys(int(i) for i in ids))[:MAX_IDS]
        if len(ids) < MIN_IDS:
            return {"error": f"Se necesitan entre {MIN_IDS} y {MAX_IDS} estrategias para comparar."}

        strategies = {
            s.id: s for s in StrategyDefinition.objects
            .select_related("asset").filter(id__in=ids)
        }
        missing = [i for i in ids if i not in strategies]
        if missing:
            return {"error": f"Estrategias no encontradas: {missing}."}

        items = []
        series: dict[str, dict[str, float]] = {}
        for sid in ids:
            strat = strategies[sid]
            symbol = strat.asset.symbol if strat.asset else None
            stored = strat.robustness_metrics or {}
            holdout = strat.holdout_metrics or {}
            item = {
                "strategy_id": sid,
                "label": f"{symbol} {strat.interval}",
                "asset_symbol": symbol,
                "interval": strat.interval,
                "description": describe_spec(strat.spec),
                "spec_hash": strat.spec_hash,
                "generated_at": strat.generated_at.isoformat() if strat.generated_at else None,
                "stored": {
                    "fitness": strat.fitness,
                    "sharpe": stored.get("sharpe"),
                    "mean_oos_sharpe": stored.get("mean_oos_sharpe"),
                    "pbo": stored.get("pbo"),
                    "wf_efficiency": stored.get("wf_efficiency"),
                    "n_trades": stored.get("n_trades"),
                    "max_drawdown_pct": stored.get("max_drawdown_pct"),
                    "cross_consistency": stored.get("cross_consistency"),
                    "holdout_return_pct": holdout.get("return_pct"),
                    "holdout_sharpe": holdout.get("sharpe"),
                },
                "fresh": {"available": False},
            }
            if symbol:
                run = run_strategy_on_recent(strat, symbol, strat.interval)
                if run is not None:
                    eq = np.asarray(run["equity"], dtype=float)
                    base = eq[0] if eq.size and eq[0] > 0 else 1.0
                    ppy = metrics.annualization_factor(strat.interval)
                    try:
                        wf = walk_forward_oos(run["df"], strat.spec, n_splits=4, ppy=ppy)
                        fresh_oos, fresh_eff = wf["mean_oos_sharpe"], wf["efficiency"]
                    except Exception as exc:  # noqa: BLE001 — el WF fresco es opcional
                        logger.warning("compare wf %s: %s", sid, exc)
                        fresh_oos = fresh_eff = None
                    item["fresh"] = {
                        "available": True,
                        "candles": len(run["df"]),
                        "data_source": run["data_source"],
                        "equity": _downsample((eq / base).tolist()),
                        "window_return_pct": run["window_return_pct"],
                        "oos_sharpe": fresh_oos,
                        "wf_efficiency": fresh_eff,
                    }
                    series[item["label"]] = run["returns"]
            items.append(item)

        # ── Correlación entre estrategias (ventana común de retornos diarios) ──
        correlation = None
        best_pair = None
        if len(series) >= 2:
            dates, aligned = align_returns(series)
            if len(dates) >= 5:
                labels, matrix = correlation_matrix(aligned)
                correlation = {"labels": labels, "matrix": matrix, "common_days": len(dates)}
                lowest = None
                for i in range(len(labels)):
                    for j in range(i + 1, len(labels)):
                        c = matrix[i][j]
                        if c is None:
                            continue
                        if lowest is None or abs(c) < abs(lowest[2]):
                            lowest = (labels[i], labels[j], c)
                if lowest:
                    best_pair = {"a": lowest[0], "b": lowest[1], "corr": round(lowest[2], 3)}

        # ── Veredictos por dimensión (cada uno responde a una pregunta) ──
        def _best(key_fn, items_subset):
            cands = [(key_fn(it), it["label"]) for it in items_subset if key_fn(it) is not None]
            return max(cands)[1] if cands else None

        verdicts = {
            "best_fitness": _best(lambda it: it["stored"]["fitness"], items),
            "best_holdout": _best(lambda it: it["stored"]["holdout_return_pct"], items),
            "best_fresh": _best(
                lambda it: it["fresh"].get("window_return_pct") if it["fresh"]["available"] else None,
                items),
            "best_generalization": _best(lambda it: it["stored"]["cross_consistency"], items),
            "most_diversifying_pair": best_pair,
        }

        return {
            "status": "OK",
            "items": items,
            "correlation": correlation,
            "verdicts": verdicts,
            "note": ("Comparador cara a cara: evidencia original + re-ejecución fresca "
                     "(equity normalizada como crecimiento de 1€) + correlación entre "
                     "estrategias. No hay un 'ganador único': cada dimensión responde a "
                     "una pregunta distinta. No constituye consejo financiero."),
        }
