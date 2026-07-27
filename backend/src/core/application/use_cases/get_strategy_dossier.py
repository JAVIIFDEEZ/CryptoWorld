"""
get_strategy_dossier.py — Dossier de auditoría de una estrategia guardada.

Reúne en un único documento TODA la evidencia de una estrategia validada:
  · Identidad y ADN: descripción legible, spec completo, hash, activo, marco.
  · Robustez ALMACENADA en su generación (gating, holdout, cross-asset): la
    evidencia original, inmutable, con la que se aprobó.
  · Análisis FRESCO sobre datos actuales: curva de equity reciente y matriz
    walk-forward — ¿sigue viva o se ha degradado desde que se generó?
  · Track record real: carteras de paper trading del usuario que la siguen.

Es el documento que un desk imprime para el comité de riesgo: evidencia
original + estado actual + resultados en vivo, con su hash como identidad.
La parte fresca se cachea; si los datos no están disponibles, el dossier se
sirve igualmente con la evidencia almacenada (degradación honesta).
"""

import logging

logger = logging.getLogger(__name__)

_FRESH_CACHE_TTL = 900          # 15 min
_FRESH_LIMIT = 500              # velas del análisis fresco


class GetStrategyDossierUseCase:

    def execute(self, strategy_id: int, owner=None) -> dict:
        from core.infrastructure.persistence.models import StrategyDefinition

        obj = (StrategyDefinition.objects.select_related("asset")
               .filter(id=strategy_id).first())
        if obj is None:
            return {"error": "Estrategia no encontrada."}

        from core.domain.services.strategy_spec import describe_spec

        dossier = {
            "status": "OK",
            "identity": {
                "strategy_id": obj.id,
                "name": obj.name,
                "description": describe_spec(obj.spec),
                "spec": obj.spec,
                "spec_hash": obj.spec_hash,
                "asset_symbol": obj.asset.symbol if obj.asset else None,
                "asset_name": obj.asset.name if obj.asset else None,
                "interval": obj.interval,
                "rank": obj.rank,
                "fitness": obj.fitness,
                "status": obj.status,
                "is_monitored": obj.is_monitored,
                "last_signal": obj.last_signal,
                "last_signal_at": obj.last_signal_at.isoformat() if obj.last_signal_at else None,
                "generated_at": obj.generated_at.isoformat() if obj.generated_at else None,
                "created_at": obj.created_at.isoformat() if obj.created_at else None,
            },
            "stored_evidence": {
                "robustness_metrics": obj.robustness_metrics,
                "gating_checks": obj.gating_checks,
                "holdout_metrics": obj.holdout_metrics,
                "note": ("Evidencia ORIGINAL de la generación: métricas del gating de "
                         "robustez y validación en el tramo holdout jamás visto por la "
                         "evolución. Inmutable desde la aprobación."),
            },
            "fresh_analysis": self._fresh_analysis(obj),
            "track_record": self._track_record(obj, owner),
            "note": ("Dossier de auditoría: evidencia original + estado actual + track "
                     "record real, identificados por el hash del spec. No constituye "
                     "consejo financiero."),
        }
        return dossier

    @staticmethod
    def _fresh_analysis(obj) -> dict:
        """Curva de equity y matriz walk-forward sobre datos ACTUALES (cacheado)."""
        from django.core.cache import cache

        cache_key = f"strategy_dossier_fresh:{obj.id}"
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

        symbol = obj.asset.symbol if obj.asset else None
        if not symbol:
            return {"available": False, "note": "La estrategia no tiene activo asociado."}
        try:
            from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
            from core.domain.services import backtest_metrics as metrics
            from core.domain.services.strategy_evaluation import (
                equity_curve, walk_forward_matrix,
            )

            res = fetch_ohlcv_dataframe(symbol=symbol, interval=obj.interval, limit=_FRESH_LIMIT)
            if res is None or res.df.empty or len(res.df) < 120:
                return {"available": False,
                        "note": f"Datos insuficientes de {symbol} para el análisis fresco."}

            ppy = metrics.annualization_factor(obj.interval)
            out = {
                "available": True,
                "candles": len(res.df),
                "data_source": res.source,
                "equity": equity_curve(res.df, obj.spec, points=160),
                "walk_forward_matrix": walk_forward_matrix(res.df, obj.spec, ppy=ppy),
            }
            cache.set(cache_key, out, _FRESH_CACHE_TTL)
            return out
        except Exception as exc:  # noqa: BLE001 — el dossier vive sin la parte fresca
            logger.warning("dossier fresh %s: %s", obj.id, exc)
            return {"available": False, "note": f"Análisis fresco no disponible: {exc}"}

    @staticmethod
    def _track_record(obj, owner) -> dict:
        """Carteras de paper trading DEL USUARIO que siguen esta estrategia."""
        from core.infrastructure.persistence.models import PaperTradingAccount

        if owner is None:
            return {"accounts": [], "note": "Sin usuario: track record no disponible."}
        accounts = []
        for a in PaperTradingAccount.objects.filter(strategy=obj, owner=owner):
            equity = float(a.cash or 0) + float(a.units or 0) * float(a.last_price or 0)
            initial = float(a.initial_capital or 0)
            accounts.append({
                "account_id": a.id,
                "started_at": a.started_at.isoformat() if a.started_at else None,
                "is_active": a.is_active,
                "initial_capital": initial,
                "equity": round(equity, 2),
                "total_return_pct": round((equity / initial - 1) * 100, 2) if initial > 0 else None,
                "realized_pnl": round(float(a.realized_pnl or 0), 2),
                "in_position": (a.units or 0) > 0,
                "live_enabled": a.live_enabled,
                "decayed": a.decayed,
            })
        return {
            "accounts": accounts,
            "note": ("Carteras de paper trading del usuario que siguen esta estrategia: "
                     "el único rendimiento aquí es el observado en vivo, no simulado."),
        }
