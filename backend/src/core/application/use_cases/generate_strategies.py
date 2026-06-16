"""
generate_strategies.py — Caso de uso: generador de estrategias por GA (Módulo 2).

Orquesta el algoritmo genético (dominio) con la suite de robustez (Módulo 1) y
materializa el principio anti data-snooping:

  ┌──────────────── serie temporal OHLCV ────────────────┐
  │  EVOLUCIÓN (1-holdout)              │  VALIDACIÓN FINAL │
  │  · fitness = Sharpe OOS walk-forward (penaliza        │  (intacta: NO se
  │    sobreajuste y bajo nº de trades)                    │   ve en la
  │  · gating de robustez (PBO, lookahead, MC, eficiencia)│   evolución ni en
  │                                                        │   el walk-forward)
  └────────────────────────────────────────────────────────────────────────┘

La partición de validación final (holdout) NO interviene ni en el fitness del GA
ni en el walk-forward ni en el gating: los finalistas se re-evalúan sobre ella
solo para REPORTAR su rendimiento en datos jamás vistos. La selección y el
ranking se deciden con métricas de la zona de evolución, de modo que el holdout
nunca contamina la elección (eso sería, en sí mismo, data-snooping).

`generate_strategies(df, ...)` es puro (solo dominio) y testeable sin red ni
Celery. `GenerateStrategiesUseCase` lo envuelve obteniendo el OHLCV y persistiendo
los finalistas robustos como StrategyDefinition (Módulo 0).
"""

import logging
from dataclasses import asdict, dataclass

import numpy as np

from core.domain.services import backtest_metrics as metrics
from core.domain.services.strategy_evaluation import (
    GatingThresholds,
    evaluate_fitness,
    gate_spec,
    holdout_performance,
)
from core.domain.services.strategy_generator import GAConfig, evolve
from core.domain.services.strategy_spec import describe_spec, spec_hash

logger = logging.getLogger(__name__)

# Velas mínimas: tras reservar el holdout, la zona de evolución aún necesita
# varios tramos walk-forward con tamaño suficiente.
MIN_CANDLES = 300


@dataclass(frozen=True)
class GenerationConfig:
    """Parámetros del generador (GA + gating + partición), todos configurables."""
    holdout_fraction: float = 0.2      # tramo de validación final reservado
    top_k: int = 5                     # nº de finalistas robustos a reportar
    max_gating_attempts: int = 12      # tope de candidatos a pasar por el gating (coste)
    ga: GAConfig = GAConfig()
    gating: GatingThresholds = GatingThresholds()


# Presets de cómputo: el GA hace cientos de walk-forwards, así que el usuario
# elige cuánto exhaustividad/espera quiere.
_PRESETS = {
    "fast": GenerationConfig(
        top_k=3, max_gating_attempts=6,
        ga=GAConfig(population_size=24, generations=8, elitism=3, random_injection=2),
        gating=GatingThresholds(wf_splits=3, pbo_neighbors=8, mc_sims=200),
    ),
    "balanced": GenerationConfig(
        top_k=5, max_gating_attempts=12,
        ga=GAConfig(population_size=40, generations=15, elitism=4, random_injection=2),
        gating=GatingThresholds(wf_splits=4, pbo_neighbors=12, mc_sims=400),
    ),
    "thorough": GenerationConfig(
        top_k=6, max_gating_attempts=18,
        ga=GAConfig(population_size=60, generations=25, elitism=6, random_injection=3),
        gating=GatingThresholds(wf_splits=4, pbo_neighbors=16, mc_sims=800),
    ),
}
DEFAULT_PRESET = "balanced"


def config_for_preset(preset: str) -> GenerationConfig:
    return _PRESETS.get(preset, _PRESETS[DEFAULT_PRESET])


def _json_safe(value):
    """inf/nan → None recursivamente (el payload pasa por JSON DRF/Celery-Redis)."""
    if isinstance(value, float):
        return value if np.isfinite(value) else None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _partition(df, holdout_fraction: float):
    """Corte temporal: [evolución | validación final]. El holdout es el tramo
    MÁS RECIENTE, jamás visto durante la evolución (anti data-snooping)."""
    n = len(df)
    split = int(round(n * (1.0 - holdout_fraction)))
    split = max(MIN_CANDLES // 2, min(split, n - 30))  # garantiza ambos tramos usables
    df_evo = df.iloc[:split].reset_index(drop=True)
    df_holdout = df.iloc[split:].reset_index(drop=True)
    return df_evo, df_holdout, split


def generate_strategies(
    df,
    interval: str = "1d",
    config: GenerationConfig | None = None,
    initial_capital: float = 10000.0,
) -> dict:
    """
    Genera estrategias por GA y devuelve el informe con el ranking de finalistas
    que pasan el gating de robustez. Función pura (solo dominio).
    """
    cfg = config or GenerationConfig()
    ppy = metrics.annualization_factor(interval)

    # ── PASO 5: partición anti data-snooping ──────────────────────────
    df_evo, df_holdout, split = _partition(df, cfg.holdout_fraction)

    # ── PASO 3: fitness robustez-aware SOLO sobre la zona de evolución ──
    def fitness_fn(spec: dict) -> float:
        return evaluate_fitness(df_evo, spec, n_splits=cfg.gating.wf_splits, ppy=ppy)["fitness"]

    ga_result = evolve(fitness_fn, cfg.ga)

    # ── PASO 4: gating de robustez de los mejores candidatos ──────────
    # Recorremos la población ordenada por fitness; el holdout (PASO 5) se mide
    # pero NO decide la selección/ranking (sería snooping de la validación).
    finalists: list[dict] = []
    attempts = 0
    for cand in ga_result["population"]:
        if attempts >= cfg.max_gating_attempts:
            break
        attempts += 1
        spec = cand["spec"]
        gate = gate_spec(df_evo, spec, cfg.gating, ppy=ppy)
        holdout = holdout_performance(df_holdout, spec, ppy=ppy)
        finalists.append({
            "spec": spec,
            "spec_hash": spec_hash(spec),
            "description": describe_spec(spec),
            "fitness": cand["fitness"],
            "passed_gating": gate["passed"],
            "gating": {"checks": gate["checks"], "metrics": gate["metrics"]},
            "evolution_metrics": {
                "fitness": cand["fitness"],
                "wf_efficiency": gate["metrics"]["wf_efficiency"],
                "mean_oos_sharpe": gate["metrics"]["mean_oos_sharpe"],
                "pbo": gate["metrics"]["pbo"],
            },
            "holdout_validation": holdout,
        })
        if sum(1 for f in finalists if f["passed_gating"]) >= cfg.top_k:
            break

    # Ranking: solo los que PASAN el gating, ordenados por fitness (métrica de
    # evolución robustez-aware). El holdout se reporta como confirmación intacta.
    passed = sorted(
        (f for f in finalists if f["passed_gating"]),
        key=lambda f: f["fitness"], reverse=True,
    )[:cfg.top_k]
    rejected = [f for f in finalists if not f["passed_gating"]]
    for rank, f in enumerate(passed, start=1):
        f["rank"] = rank

    # Coordenadas de robustez de CADA candidata evaluada (pase o no el gating):
    # alimentan el grafico 3D "universo de robustez" con la nube completa de
    # puntos, no solo las supervivientes.
    def _coords(f: dict) -> dict:
        m = f["gating"]["metrics"]
        return {
            "spec_hash": f["spec_hash"],
            "description": f["description"],
            "fitness": f["fitness"],
            "passed_gating": f["passed_gating"],
            "pbo": m.get("pbo"),
            "wf_efficiency": m.get("wf_efficiency"),
            "oos_sharpe": m.get("mean_oos_sharpe"),
            "sharpe": m.get("sharpe"),
            "n_trades": m.get("n_trades"),
            "total_return_pct": m.get("total_return_pct"),
            "max_drawdown_pct": m.get("max_drawdown_pct"),
        }

    report = {
        "interval": interval,
        "initial_capital": initial_capital,
        "candles_total": len(df),
        "data_partition": {
            "evolution_candles": len(df_evo),
            "holdout_candles": len(df_holdout),
            "holdout_fraction": cfg.holdout_fraction,
            "split_index": split,
            "note": (
                "El tramo de validación final (holdout) son las velas más recientes. "
                "No interviene en el fitness del GA, ni en el walk-forward, ni en el "
                "gating; los finalistas se miden en él solo para reportar su "
                "rendimiento en datos jamás vistos."
            ),
        },
        "ga_config": asdict(cfg.ga),
        "gating_thresholds": asdict(cfg.gating),
        "ga_evolution": {
            "history": ga_result["history"],
            "evaluations": ga_result["evaluations"],
            "best_fitness": ga_result["best"]["fitness"],
        },
        "summary": {
            "candidates_gated": len(finalists),
            "passed_gating": len(passed),
            "rejected": len(rejected),
        },
        "ranking": passed,
        "candidates": [_coords(f) for f in finalists],
        "rejected": [
            {
                **_coords(f),
                "failed_checks": [k for k, v in f["gating"]["checks"].items() if not v],
            }
            for f in rejected
        ],
    }
    return _json_safe(report)


class GenerateStrategiesUseCase:
    """Carga el OHLCV, ejecuta el generador y persiste los finalistas robustos."""

    def execute(
        self,
        asset_symbol: str,
        interval: str = "1d",
        limit: int = 730,
        initial_capital: float = 10000.0,
        preset: str = DEFAULT_PRESET,
        config: GenerationConfig | None = None,
        persist: bool = True,
    ) -> dict:
        # Import diferido: mantiene generate_strategies (dominio puro) importable
        # sin arrastrar infraestructura/Django.
        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe

        symbol = asset_symbol.upper()
        result = fetch_ohlcv_dataframe(symbol=symbol, interval=interval, limit=limit)
        if result is None or result.df.empty or len(result.df) < MIN_CANDLES:
            return {
                "error": (
                    f"Se necesitan al menos {MIN_CANDLES} velas para generar "
                    f"estrategias robustas y no hay suficientes datos para {symbol}."
                ),
            }

        cfg = config or config_for_preset(preset)
        report = generate_strategies(
            result.df, interval=interval, config=cfg, initial_capital=initial_capital,
        )
        report["asset_symbol"] = symbol
        report["data_source"] = result.source
        report["preset"] = preset

        if persist:
            report["persisted"] = self._persist(symbol, interval, report)

        logger.info(
            "generate_strategies %s [%s]: %d/%d finalistas pasan el gating",
            symbol, preset, report["summary"]["passed_gating"], report["summary"]["candidates_gated"],
        )
        return report

    @staticmethod
    def _persist(symbol: str, interval: str, report: dict) -> list[dict]:
        """Persiste cada finalista del ranking como StrategyDefinition (Módulo 0)."""
        from django.utils import timezone
        from core.infrastructure.persistence.models import CryptoAsset, StrategyDefinition

        asset = CryptoAsset.objects.filter(symbol=symbol).first()
        persisted = []
        for item in report["ranking"]:
            obj = StrategyDefinition.objects.create(
                asset=asset,
                name=item["description"][:255],
                spec=item["spec"],
                spec_hash=item["spec_hash"],
                interval=interval,
                rank=item["rank"],
                fitness=item["fitness"],
                passed_gating=item["passed_gating"],
                robustness_metrics=item["gating"]["metrics"],
                gating_checks=item["gating"]["checks"],
                holdout_metrics=item["holdout_validation"],
                status="validated",
                generated_at=timezone.now(),
            )
            persisted.append({"id": obj.id, "spec_hash": obj.spec_hash, "rank": obj.rank})
        return persisted
