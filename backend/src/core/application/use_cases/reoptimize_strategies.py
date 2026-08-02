"""
reoptimize_strategies.py — Reoptimización programada y mejor estrategia por activo.

Una estrategia que fue robusta en el pasado se degrada cuando el régimen de
mercado cambia (lo que el monitor de drift detecta). La respuesta es reoptimizar:
volver a correr el generador genético sobre datos frescos y quedarse con la mejor
estrategia validada de cada activo.

Esta reoptimización es DIRIGIDA y barata: solo regenera los activos que el usuario
sigue de verdad (con paper trading activo o monitorización), no todo el universo.
Deduplica por spec_hash para no inflar el histórico con estrategias idénticas, y
expone la "campeona" actual de cada activo con su track record en vivo.
"""

import logging

logger = logging.getLogger(__name__)


def _tracked_pairs() -> list[tuple[str, str]]:
    """Pares (símbolo, intervalo) que el usuario sigue: con paper trading activo o
    estrategia monitorizada. Son los que merece la pena reoptimizar."""
    from core.infrastructure.persistence.models import PaperTradingAccount, StrategyDefinition

    pairs = set()
    for sym, interval in (
        PaperTradingAccount.objects.filter(is_active=True)
        .values_list("asset_symbol", "interval").distinct()
    ):
        if sym:
            pairs.add((sym.upper(), interval))
    for sym, interval in (
        StrategyDefinition.objects.filter(is_monitored=True, asset__isnull=False)
        .values_list("asset__symbol", "interval").distinct()
    ):
        if sym:
            pairs.add((sym.upper(), interval))
    return sorted(pairs)


class ReoptimizeStrategiesUseCase:
    """Regenera las estrategias de los activos seguidos y persiste solo las nuevas
    (dedup por spec_hash). Pensada para Celery beat (p. ej. semanal)."""

    def execute(self, preset: str = "balanced", limit_pairs: int = 12,
                pairs: list[tuple[str, str]] | None = None) -> dict:
        from core.application.use_cases.generate_strategies import GenerateStrategiesUseCase
        from core.infrastructure.persistence.models import CryptoAsset, StrategyDefinition

        # `pairs` explícito: reoptimización dirigida (p. ej. de un activo decaído);
        # si no, los activos seguidos (ciclo programado).
        pairs = (pairs if pairs is not None else _tracked_pairs())[:limit_pairs]
        summary = {"pairs": len(pairs), "new_strategies": 0, "regenerated": 0, "details": []}

        for symbol, interval in pairs:
            try:
                report = GenerateStrategiesUseCase().execute(
                    asset_symbol=symbol, interval=interval, preset=preset, persist=False,
                )
            except Exception as exc:  # noqa: BLE001 — un activo no debe tumbar la pasada
                logger.warning("reoptimize %s/%s falló: %s", symbol, interval, exc)
                summary["details"].append({"asset_symbol": symbol, "interval": interval, "error": str(exc)})
                continue
            if report.get("error"):
                summary["details"].append({"asset_symbol": symbol, "interval": interval, "error": report["error"]})
                continue

            summary["regenerated"] += 1
            asset = CryptoAsset.objects.filter(symbol=symbol).first()
            existing = set(
                StrategyDefinition.objects
                .filter(asset=asset, interval=interval)
                .values_list("spec_hash", flat=True)
            )
            new_count = self._persist_new(asset, interval, report, existing)
            summary["new_strategies"] += new_count
            summary["details"].append({
                "asset_symbol": symbol, "interval": interval,
                "passed_gating": report["summary"]["passed_gating"], "new": new_count,
            })

        logger.info("reoptimize_strategies: %d pares, %d nuevas estrategias",
                    summary["regenerated"], summary["new_strategies"])
        return summary

    @staticmethod
    def _persist_new(asset, interval: str, report: dict, existing: set) -> int:
        """Persiste los finalistas cuyo spec_hash es nuevo para el activo.

        El estado lo decide el mismo criterio que en la generación manual:
        «validada» exige holdout positivo, no solo haber pasado el gating.
        """
        from django.utils import timezone
        from core.application.use_cases.generate_strategies import _status_for
        from core.infrastructure.persistence.models import StrategyDefinition

        created = 0
        for item in report["ranking"]:
            if not item.get("passed_gating") or item["spec_hash"] in existing:
                continue
            StrategyDefinition.objects.create(
                asset=asset,
                name=item["description"][:255],
                spec=item["spec"],
                spec_hash=item["spec_hash"],
                interval=interval,
                rank=item["rank"],
                fitness=item["fitness"],
                passed_gating=True,
                robustness_metrics=item["gating"]["metrics"],
                gating_checks=item["gating"]["checks"],
                holdout_metrics=item["holdout_validation"],
                status=_status_for(item),
                generated_at=timezone.now(),
            )
            existing.add(item["spec_hash"])
            created += 1
        return created


class FillStrategyStableUseCase:
    """
    Establo nocturno: mantiene una campeona validada FRESCA para cada activo que
    importa (watchlists de los usuarios + top por capitalización) sin intervención
    manual. Cada noche detecta los activos SIN estrategia validada reciente
    (< `stale_days`) y genera solo para esos, con un tope por pasada — en régimen
    estacionario casi todo está cubierto y la tarea es barata. Delegando en
    ReoptimizeStrategiesUseCase hereda dedup por spec_hash y tolerancia a fallos.
    """

    def execute(self, preset: str = "balanced", interval: str = "1d",
                per_night: int = 2, stale_days: int = 30, top_assets: int = 8) -> dict:
        from datetime import timedelta
        from django.utils import timezone
        from core.infrastructure.persistence.models import (
            CryptoAsset, StrategyDefinition, UserWatchlist,
        )

        # Universo que importa: watchlists de todos los usuarios + top por cap.
        universe: set[str] = set(
            UserWatchlist.objects.values_list("asset__symbol", flat=True)
        )
        universe.update(
            CryptoAsset.objects.exclude(market_cap__isnull=True)
            .order_by("-market_cap").values_list("symbol", flat=True)[:top_assets]
        )
        universe.discard(None)

        # Cubierto = tiene una validada fresca; lo demás es hueco del establo.
        cutoff = timezone.now() - timedelta(days=stale_days)
        covered = {
            c.upper() for c in StrategyDefinition.objects
            .filter(interval=interval, passed_gating=True, status="validated",
                    generated_at__gte=cutoff, asset__isnull=False)
            .values_list("asset__symbol", flat=True)
        }
        gaps = sorted(s for s in universe if s and s.upper() not in covered)
        todo = gaps[:per_night]

        result = {
            "universe": len(universe), "covered": len(universe) - len(gaps),
            "gaps": len(gaps), "generated_for": todo,
        }
        if todo:
            summary = ReoptimizeStrategiesUseCase().execute(
                preset=preset, pairs=[(s, interval) for s in todo],
            )
            result["new_strategies"] = summary["new_strategies"]
            result["details"] = summary["details"]
        else:
            result["new_strategies"] = 0
            result["details"] = []

        logger.info("fill_strategy_stable: %d huecos, generadas %d nuevas para %s",
                    len(gaps), result["new_strategies"], todo or "—")
        return result


class BestStrategiesUseCase:
    """Campeona actual de cada activo: la mejor estrategia validada (por fitness),
    con su rendimiento en holdout y su track record en vivo (paper trading)."""

    def execute(self, owner=None, interval: str | None = None) -> dict:
        from core.infrastructure.persistence.models import PaperTradingAccount, StrategyDefinition

        qs = StrategyDefinition.objects.select_related("asset").filter(
            passed_gating=True, asset__isnull=False,
        )
        if interval:
            qs = qs.filter(interval=interval)

        # Campeona = mayor fitness por (activo, intervalo). Recorriendo en orden
        # descendente de fitness, la primera vista de cada par es su campeona.
        champions = []
        seen = set()
        for s in qs.order_by("-fitness"):
            key = (s.asset_id, s.interval)
            if key in seen:
                continue
            seen.add(key)
            champions.append(s)

        # Track record en vivo del usuario para cada estrategia campeona.
        paper_by_strategy: dict = {}
        if champions:
            paper_qs = PaperTradingAccount.objects.filter(
                strategy_id__in=[c.id for c in champions],
            )
            if owner is not None and getattr(owner, "is_authenticated", False):
                paper_qs = paper_qs.filter(owner=owner)
            for acc in paper_qs:
                paper_by_strategy.setdefault(acc.strategy_id, acc)

        results = []
        for s in champions:
            acc = paper_by_strategy.get(s.id)
            results.append({
                "strategy_id": s.id,
                "asset_symbol": s.asset.symbol if s.asset else None,
                "name": s.name,
                "interval": s.interval,
                "fitness": s.fitness,
                "holdout_return_pct": (s.holdout_metrics or {}).get("return_pct"),
                "holdout_sharpe": (s.holdout_metrics or {}).get("sharpe"),
                "generated_at": s.generated_at.isoformat() if s.generated_at else None,
                "is_monitored": s.is_monitored,
                "live": (
                    {
                        "account_id": acc.id,
                        "total_return_pct": round(acc.total_return_pct, 4),
                        "realized_pnl": round(acc.realized_pnl, 2),
                        "trades_count": acc.trades_count,
                        "is_active": acc.is_active,
                    }
                    if acc else None
                ),
            })
        return {"count": len(results), "results": results}
