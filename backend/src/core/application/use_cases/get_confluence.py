"""
get_confluence.py — Caso de uso: motor de confluencia 360° por activo.

Reúne las cuatro fuentes del sistema, cada una normalizada a [-1, +1]:
  · technical — dashboard multi-indicador en 4h y 1d (media de ambos marcos).
  · ml        — probabilidad calibrada del ensemble ((prob_up − 0.5)·2),
                amortiguada al 50% si el veredicto OOS es NO_EDGE.
  · onchain   — presión de flujo a/desde exchanges (contexto de mercado,
                ventana 24h del escáner propio).
  · news      — sentimiento neto del feed del activo ((pos − neg)/total).

Los pesos se APRENDEN del acierto histórico real de cada fuente (lecturas
resueltas de ConfluenceSnapshot; dominio confluence_fusion.learn_weights) y
cada lectura direccional se registra para resolverse a las 24h — el motor
mejora con su propio uso. Cada fuente cae con degradación parcial: la
confluencia funciona con las que estén vivas y lo dice.
"""

import logging

from core.domain.services.confluence_fusion import (
    DIRECTIONAL_MIN, PRIOR_WEIGHTS, clamp, engine_track_record, fuse,
    learn_weights_hierarchical,
)

logger = logging.getLogger(__name__)

_LEARN_WINDOW = 400      # últimas lecturas resueltas usadas para aprender pesos
_HORIZON_HOURS = 24
_SIGNAL_CANDLES = 200


class GetConfluenceUseCase:

    def execute(self, symbol: str) -> dict:
        symbol = (symbol or "").upper().strip()
        if not symbol:
            return {"error": "Falta el símbolo."}

        sources = {
            "technical": self._technical(symbol),
            "ml": self._ml(symbol),
            "onchain": self._onchain(),
            "news": self._news(symbol),
        }
        weights = self._learned_weights(symbol)
        fused = fuse(sources, weights)

        last_price = sources["technical"].get("last_price") or self._last_price(symbol)
        self._log_snapshot(symbol, sources, fused, last_price)

        return {
            "asset_symbol": symbol,
            **fused,
            "sources": {
                name: {**{k: v for k, v in src.items() if k != "last_price"},
                       "weight": weights[name]["weight"],
                       "weight_mode": weights[name]["mode"],
                       "hit_rate": weights[name]["hit_rate"],
                       "sample": weights[name]["n"]}
                for name, src in sources.items()
            },
            "track_record": self._track_record(),
            "horizon_hours": _HORIZON_HOURS,
            "note": (
                "Score por fuente ∈ [-1, +1]. Los pesos se aprenden del acierto "
                "histórico real de cada fuente sobre lecturas verificadas a "
                f"{_HORIZON_HOURS}h; sin muestra suficiente se usan pesos a "
                "priori (se indica por fuente). No constituye consejo financiero."
            ),
        }

    # ── Fuentes (cada una con degradación parcial) ──────────────────

    @staticmethod
    def _technical(symbol: str) -> dict:
        """Dashboard multi-indicador en 4h y 1d: media de los scores."""
        try:
            from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
            from core.domain.services.technical_analysis_service import (
                calculate_signals_dashboard,
            )
            scores, last_price = [], None
            for interval in ("4h", "1d"):
                res = fetch_ohlcv_dataframe(symbol=symbol, interval=interval,
                                            limit=_SIGNAL_CANDLES)
                if res is None or res.df.empty:
                    continue
                dash = calculate_signals_dashboard(res.df)
                scores.append(clamp(dash["summary"]["score"]))
                last_price = float(res.df["close"].iloc[-1])
            if not scores:
                return {"available": False, "score": None,
                        "detail": "Sin datos OHLCV para el dashboard técnico."}
            score = sum(scores) / len(scores)
            return {"available": True, "score": round(score, 4),
                    "detail": f"Dashboard multi-indicador en 4h y 1d ({len(scores)} marcos).",
                    "last_price": last_price}
        except Exception as exc:  # noqa: BLE001
            logger.warning("confluence technical %s: %s", symbol, exc)
            return {"available": False, "score": None, "detail": "Fuente técnica no disponible."}

    @staticmethod
    def _ml(symbol: str) -> dict:
        """Probabilidad calibrada del ensemble, amortiguada sin edge OOS."""
        try:
            from core.application.dto.asset_dto import PredictionRequestDTO
            from core.application.use_cases.predict_price import PredictPriceUseCase

            pred = PredictPriceUseCase().execute(
                PredictionRequestDTO(asset_symbol=symbol, interval="1h", horizon=5),
                owner=None, log=False,
            )
            prob_up = pred.get("prob_up")
            if pred.get("error") or prob_up is None:
                return {"available": False, "score": None,
                        "detail": pred.get("error") or "Predicción no disponible."}
            score = (float(prob_up) - 0.5) * 2.0
            verdict = pred.get("verdict")
            if verdict == "NO_EDGE":
                score *= 0.5   # sin edge fuera de muestra: la opinión vale menos
            return {"available": True, "score": round(clamp(score), 4),
                    "detail": f"prob_up calibrada {prob_up:.0%} · veredicto {verdict or '—'}"
                              + (" (amortiguado ×0.5 por NO_EDGE)" if verdict == "NO_EDGE" else "")}
        except Exception as exc:  # noqa: BLE001
            logger.warning("confluence ml %s: %s", symbol, exc)
            return {"available": False, "score": None, "detail": "Fuente ML no disponible."}

    @staticmethod
    def _onchain() -> dict:
        """Presión de flujo a/desde exchanges (contexto de mercado, 24h)."""
        try:
            from core.application.use_cases.onchain_pressure import OnChainPressureUseCase

            p = OnChainPressureUseCase().execute(chain="ethereum", hours=24)
            if p.get("error") or p.get("verdict") == "INSUFICIENTE":
                return {"available": False, "score": None,
                        "detail": "Muestra on-chain insuficiente en 24h."}
            return {"available": True, "score": round(clamp(p["pressure"]), 4),
                    "detail": f"Presión de exchanges 24h: {p['verdict']} "
                              "(contexto de mercado, red ethereum)."}
        except Exception as exc:  # noqa: BLE001
            logger.warning("confluence onchain: %s", exc)
            return {"available": False, "score": None, "detail": "Fuente on-chain no disponible."}

    @staticmethod
    def _news(symbol: str) -> dict:
        """Sentimiento neto del feed de noticias del activo."""
        try:
            from core.application.use_cases.get_news_feed import GetNewsFeedUseCase

            feed = GetNewsFeedUseCase().execute(query=symbol, sentiment="", limit=30)
            items = feed.get("items") or []
            if feed.get("error") or len(items) < 5:
                return {"available": False, "score": None,
                        "detail": "Menos de 5 noticias del activo: sin señal."}
            pos = sum(1 for i in items if getattr(i, "sentiment", None) == "positive")
            neg = sum(1 for i in items if getattr(i, "sentiment", None) == "negative")
            score = (pos - neg) / len(items)
            return {"available": True, "score": round(clamp(score), 4),
                    "detail": f"{len(items)} noticias: {pos} positivas, {neg} negativas."}
        except Exception as exc:  # noqa: BLE001
            logger.warning("confluence news %s: %s", symbol, exc)
            return {"available": False, "score": None, "detail": "Fuente de noticias no disponible."}

    # ── Aprendizaje y registro ──────────────────────────────────────

    @staticmethod
    def _learned_weights(symbol: str) -> dict:
        """Jerárquico: acierto sobre lecturas de ESTE activo si hay muestra,
        si no el global, si no los priors (el modo lo declara por fuente)."""
        try:
            from core.infrastructure.persistence.models import ConfluenceSnapshot

            base = ConfluenceSnapshot.objects.filter(status="resolved").order_by("-resolved_at")
            global_rows = list(base.values("scores", "actual_return_pct")[:_LEARN_WINDOW])
            asset_rows = list(base.filter(asset_symbol=symbol)
                              .values("scores", "actual_return_pct")[:_LEARN_WINDOW])
            return learn_weights_hierarchical(asset_rows, global_rows)
        except Exception:  # noqa: BLE001 — sin BD: pesos a priori
            return {s: {"weight": w, "hit_rate": None, "n": 0, "mode": "a_priori"}
                    for s, w in PRIOR_WEIGHTS.items()}

    @staticmethod
    def _track_record() -> dict:
        """Acierto verificado del PROPIO motor (global y por veredicto)."""
        try:
            from core.infrastructure.persistence.models import ConfluenceSnapshot

            rows = list(
                ConfluenceSnapshot.objects.filter(status="resolved")
                .order_by("-resolved_at")
                .values("fused_score", "verdict", "actual_return_pct")[:_LEARN_WINDOW]
            )
            return engine_track_record(rows)
        except Exception:  # noqa: BLE001
            return {"overall": {"n": 0, "hit_rate": None, "avg_signed_return_pct": None},
                    "by_verdict": {}}

    @staticmethod
    def _last_price(symbol: str) -> float | None:
        try:
            from core.infrastructure.persistence.models import CryptoAsset
            asset = CryptoAsset.objects.filter(symbol=symbol).first()
            return float(asset.current_price) if asset and asset.current_price else None
        except Exception:  # noqa: BLE001
            return None

    @staticmethod
    def _log_snapshot(symbol: str, sources: dict, fused: dict, price: float | None) -> None:
        """Registra la lectura para verificarla a las 24h (máx. una pendiente
        por activo: las recargas no inflan el historial de aprendizaje)."""
        if fused.get("verdict") == "INSUFICIENTE" or not price:
            return
        if abs(fused.get("score", 0.0)) < DIRECTIONAL_MIN:
            return   # solo se aprende de lecturas direccionales
        try:
            from datetime import timedelta
            from django.utils import timezone
            from core.infrastructure.persistence.models import ConfluenceSnapshot

            if ConfluenceSnapshot.objects.filter(asset_symbol=symbol, status="pending").exists():
                return
            ConfluenceSnapshot.objects.create(
                asset_symbol=symbol,
                scores={k: v.get("score") for k, v in sources.items() if v.get("available")},
                fused_score=fused["score"],
                verdict=fused["verdict"],
                price_at=float(price),
                horizon_hours=_HORIZON_HOURS,
                resolve_at=timezone.now() + timedelta(hours=_HORIZON_HOURS),
            )
        except Exception as exc:  # noqa: BLE001 — registrar nunca rompe la lectura
            logger.warning("confluence snapshot %s: %s", symbol, exc)


class ResolveConfluenceSnapshotsUseCase:
    """Resuelve las lecturas vencidas contra el precio real: el combustible del
    aprendizaje de pesos. Pensada para Celery beat."""

    def execute(self) -> dict:
        from django.utils import timezone
        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
        from core.infrastructure.persistence.models import ConfluenceSnapshot

        due = list(ConfluenceSnapshot.objects.filter(
            status="pending", resolve_at__lte=timezone.now(),
        )[:100])
        resolved = 0
        price_cache: dict[str, float | None] = {}
        for snap in due:
            if snap.asset_symbol not in price_cache:
                res = fetch_ohlcv_dataframe(symbol=snap.asset_symbol, interval="1h", limit=2)
                price_cache[snap.asset_symbol] = (
                    float(res.df["close"].iloc[-1]) if res is not None and not res.df.empty else None
                )
            price = price_cache[snap.asset_symbol]
            if price is None or snap.price_at <= 0:
                continue
            snap.actual_return_pct = round((price / snap.price_at - 1.0) * 100.0, 4)
            snap.status = "resolved"
            snap.resolved_at = timezone.now()
            snap.save(update_fields=["actual_return_pct", "status", "resolved_at"])
            resolved += 1
        logger.info("resolve_confluence: %d/%d lecturas resueltas", resolved, len(due))
        return {"due": len(due), "resolved": resolved}


class EvaluateConfluenceUseCase:
    """Evaluación programada del motor para los activos relevantes.

    Dos efectos: (1) el motor APRENDE de forma continua — cada pasada registra
    lecturas direccionales que se verificarán a las 24h aunque nadie visite la
    página; (2) los CAMBIOS de veredicto (entrar/salir/cambiar de confluencia)
    se registran como eventos y llegan al centro de notificaciones. El estado
    repetido nunca genera eventos; INSUFICIENTE ni señala ni resetea el último
    régimen conocido (sin fuentes no hay información, no un cambio)."""

    def execute(self, symbols: list[str] | None = None) -> dict:
        from django.core.cache import cache
        from core.infrastructure.persistence.models import (
            ConfluenceSignalEvent, CryptoAsset, PaperTradingAccount,
        )

        if symbols is None:
            top = list(
                CryptoAsset.objects.exclude(market_cap__isnull=True)
                .order_by("-market_cap").values_list("symbol", flat=True)[:8]
            )
            active = list(
                PaperTradingAccount.objects.filter(is_active=True)
                .values_list("asset_symbol", flat=True).distinct()
            )
            symbols = list(dict.fromkeys(top + active))

        evaluated = transitions = 0
        uc = GetConfluenceUseCase()
        for symbol in symbols:
            try:
                reading = uc.execute(symbol)
            except Exception as exc:  # noqa: BLE001 — un activo caído no frena el resto
                logger.warning("evaluate_confluence %s: %s", symbol, exc)
                continue
            verdict = reading.get("verdict")
            if reading.get("error") or verdict in (None, "INSUFICIENTE"):
                continue
            evaluated += 1
            # La lectura programada también alimenta la caché del endpoint.
            cache.set(f"confluence:{symbol}", reading, 600)
            last = (ConfluenceSignalEvent.objects
                    .filter(asset_symbol=symbol).order_by("-created_at").first())
            if last is None or last.verdict != verdict:
                ConfluenceSignalEvent.objects.create(
                    asset_symbol=symbol,
                    verdict=verdict,
                    previous_verdict=last.verdict if last else "",
                    score=reading["score"],
                    agreement_pct=reading["agreement_pct"],
                )
                transitions += 1

        logger.info("evaluate_confluence: %d evaluados, %d transiciones", evaluated, transitions)
        return {"symbols": symbols, "evaluated": evaluated, "transitions": transitions}
