"""
track_predictions.py — Registro y verificación de predicciones ML.

Cierra el bucle de mejora continua: cada predicción se guarda con el precio del
momento y una fecha de resolución (cuando transcurre el horizonte). Una tarea
periódica trae el precio real de ese momento y marca la predicción como acierto
o fallo. Así se mide el rendimiento REAL en vivo del modelo (no solo el backtest
out-of-sample) y se puede vigilar/depurar su degradación.

Buenas prácticas aplicadas (model monitoring con etiqueta diferida):
  · La predicción se registra como evento inmutable en el instante en que se hace.
  · El "ground truth" llega más tarde (delayed labeling): se resuelve de forma
    asíncrona usando el precio de cierre de la vela en la fecha de resolución.
  · Las métricas realizadas se segmentan por veredicto del modelo (EDGE vs
    NO_EDGE) para verificar que el propio juicio de fiabilidad del modelo acierta.
"""

import logging
from datetime import timedelta

logger = logging.getLogger(__name__)

# Minutos por vela (para calcular cuándo se resuelve el horizonte).
_INTERVAL_MINUTES = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "2h": 120,
    "4h": 240, "6h": 360, "12h": 720, "1d": 1440, "1w": 10080,
}


def log_prediction(prediction: dict, asset_symbol: str, interval: str, horizon: int,
                   last_close: float, owner=None) -> None:
    """Registra una predicción accionable (ALCISTA/BAJISTA) para verificarla luego."""
    from django.utils import timezone
    from core.infrastructure.persistence.models import CryptoAsset, PredictionRecord

    if prediction.get("prediction") not in ("ALCISTA", "BAJISTA") or not last_close:
        return  # INSUFFICIENT_DATA u otros: no se registra

    minutes = _INTERVAL_MINUTES.get(interval, 60) * max(1, int(horizon))
    asset = CryptoAsset.objects.filter(symbol=asset_symbol.upper()).first()
    # Dedupe: una sola predicción "abierta" por (dueño, activo, marco, horizonte).
    # Evita inflar el historial con recargas; al resolverse se podrá registrar otra.
    if PredictionRecord.objects.filter(
        owner=(owner if (owner is not None and getattr(owner, "is_authenticated", False)) else None),
        asset_symbol=asset_symbol.upper(), interval=interval, horizon=int(horizon), status="pending",
    ).exists():
        return
    try:
        PredictionRecord.objects.create(
            asset=asset,
            owner=owner if (owner is not None and getattr(owner, "is_authenticated", False)) else None,
            asset_symbol=asset_symbol.upper(),
            interval=interval,
            horizon=int(horizon),
            predicted=prediction["prediction"],
            prob_up=float(prediction.get("prob_up", prediction.get("confidence", 0.5))),
            confidence=float(prediction.get("confidence", 0.5)),
            edge=prediction.get("edge"),
            oos_accuracy=prediction.get("oos_accuracy"),
            verdict=prediction.get("verdict", ""),
            model=prediction.get("model", ""),
            price_at_prediction=float(last_close),
            resolve_at=timezone.now() + timedelta(minutes=minutes),
        )
    except Exception as exc:  # noqa: BLE001 — registrar nunca debe romper la predicción
        logger.warning("log_prediction fallo %s: %s", asset_symbol, exc)


class ResolvePredictionsUseCase:
    """Resuelve las predicciones cuyo horizonte ya transcurrió, trayendo el precio
    real de ese momento y marcándolas acierto/fallo."""

    def execute(self) -> dict:
        from django.utils import timezone
        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
        from core.infrastructure.persistence.models import PredictionRecord

        now = timezone.now()
        pending = PredictionRecord.objects.filter(status="pending", resolve_at__lte=now)[:200]
        resolved = correct = 0
        # Cachear el OHLCV por (símbolo, intervalo) dentro de la pasada.
        ohlcv_cache: dict = {}

        for rec in pending:
            key = (rec.asset_symbol, rec.interval)
            if key not in ohlcv_cache:
                res = fetch_ohlcv_dataframe(symbol=rec.asset_symbol, interval=rec.interval, limit=500)
                ohlcv_cache[key] = res.df if (res and not res.df.empty) else None
            df = ohlcv_cache[key]
            price = _price_at(df, rec.resolve_at)
            if price is None:
                continue  # los datos aún no alcanzan la fecha de resolución

            actual = "ALCISTA" if price > rec.price_at_prediction else "BAJISTA"
            rec.price_at_resolution = float(price)
            rec.actual_direction = actual
            rec.actual_return_pct = round((price / rec.price_at_prediction - 1.0) * 100.0, 4) if rec.price_at_prediction else 0.0
            rec.status = "correct" if actual == rec.predicted else "incorrect"
            rec.resolved_at = now
            rec.save(update_fields=["price_at_resolution", "actual_direction",
                                    "actual_return_pct", "status", "resolved_at"])
            resolved += 1
            correct += int(rec.status == "correct")

        logger.info("resolve_predictions: %d resueltas, %d aciertos", resolved, correct)
        return {"resolved": resolved, "correct": correct}


def _price_at(df, when):
    """Cierre de la primera vela cuyo timestamp ≥ `when`. None si los datos no
    llegan aún a esa fecha."""
    if df is None or df.empty or "timestamp" not in df.columns:
        return None
    target_ms = int(when.timestamp() * 1000)
    ts = df["timestamp"].astype("int64")
    # Normaliza a ms si vinieran en segundos
    if ts.iloc[-1] < 1_000_000_000_000:
        ts = ts * 1000
    mask = ts >= target_ms
    if not mask.any():
        return None  # la última vela es anterior a la fecha de resolución
    idx = mask.idxmax()
    return float(df.loc[idx, "close"])


class PredictionTrackRecordUseCase:
    """Rendimiento realizado (en vivo) de las predicciones: precisión global,
    por veredicto del modelo y registros recientes."""

    def execute(self, owner=None, limit: int = 30) -> dict:
        from core.infrastructure.persistence.models import PredictionRecord

        qs = PredictionRecord.objects.all()
        if owner is not None and getattr(owner, "is_authenticated", False):
            qs = qs.filter(owner=owner)

        resolved = qs.filter(status__in=["correct", "incorrect"])
        total_resolved = resolved.count()
        correct = resolved.filter(status="correct").count()
        accuracy = round(correct / total_resolved, 4) if total_resolved else None

        # Precisión segmentada por veredicto: ¿acierta más cuando el modelo dijo
        # que tenía edge? (validación del propio autoconocimiento del modelo)
        by_verdict = {}
        for verdict in ("EDGE", "WEAK", "NO_EDGE"):
            sub = resolved.filter(verdict=verdict)
            n = sub.count()
            if n:
                by_verdict[verdict] = {
                    "n": n,
                    "accuracy": round(sub.filter(status="correct").count() / n, 4),
                }

        recent = [
            {
                "id": r.id,
                "asset_symbol": r.asset_symbol,
                "interval": r.interval,
                "horizon": r.horizon,
                "predicted": r.predicted,
                "confidence": r.confidence,
                "verdict": r.verdict,
                "status": r.status,
                "actual_direction": r.actual_direction or None,
                "actual_return_pct": r.actual_return_pct,
                "created_at": r.created_at.isoformat(),
                "resolve_at": r.resolve_at.isoformat(),
            }
            for r in qs.select_related("asset")[:limit]
        ]
        return {
            "total": qs.count(),
            "resolved": total_resolved,
            "pending": qs.filter(status="pending").count(),
            "correct": correct,
            "accuracy": accuracy,
            "by_verdict": by_verdict,
            "recent": recent,
        }


class PredictionMonitoringUseCase:
    """Monitorización de *drift* del modelo: compara la precisión REALIZADA en
    vivo contra la precisión out-of-sample que el modelo prometió (OOS), y la
    sigue en el tiempo para detectar degradación.

    Buenas prácticas de model monitoring:
      · *Expected vs realized*: la media de `oos_accuracy` registrada es lo que el
        modelo prometía; la precisión realizada es lo que de verdad logró. Una
        brecha negativa sostenida es la señal canónica de degradación.
      · Serie temporal por ventanas de resolución: permite ver si la precisión
        cae con el tiempo (concept drift) en lugar de un único número agregado.
      · Estado accionable (ok / watch / drift) con umbrales explícitos para poder
        disparar una alerta o una reentrenamiento/reoptimización.
    """

    # Brecha (realizado − prometido) a partir de la cual se alerta.
    _WATCH_GAP = -0.08
    _DRIFT_GAP = -0.15
    _MIN_RESOLVED = 10   # por debajo de esto no hay muestra suficiente para juzgar

    def execute(self, owner=None, buckets: int = 8) -> dict:
        from core.infrastructure.persistence.models import PredictionRecord

        qs = PredictionRecord.objects.all()
        if owner is not None and getattr(owner, "is_authenticated", False):
            qs = qs.filter(owner=owner)

        resolved = list(
            qs.filter(status__in=["correct", "incorrect"], resolved_at__isnull=False)
            .order_by("resolved_at")
            .values("status", "verdict", "oos_accuracy", "asset_symbol", "resolved_at")
        )
        n = len(resolved)

        # Precisión prometida (media de las OOS registradas) vs realizada en vivo.
        oos_vals = [r["oos_accuracy"] for r in resolved if r["oos_accuracy"] is not None]
        expected_accuracy = round(sum(oos_vals) / len(oos_vals), 4) if oos_vals else None
        n_correct = sum(1 for r in resolved if r["status"] == "correct")
        realized_accuracy = round(n_correct / n, 4) if n else None
        gap = (round(realized_accuracy - expected_accuracy, 4)
               if (expected_accuracy is not None and realized_accuracy is not None) else None)

        # Estado de drift accionable.
        if n < self._MIN_RESOLVED or gap is None:
            status_ = "insufficient"
            message = f"Aún no hay muestra suficiente ({n}/{self._MIN_RESOLVED} resueltas) para juzgar el drift."
        elif gap <= self._DRIFT_GAP:
            status_ = "drift"
            message = (f"Degradación: el modelo acierta {realized_accuracy:.0%} en vivo, "
                       f"{abs(gap):.0%} por debajo de lo prometido. Conviene reoptimizar/reentrenar.")
        elif gap <= self._WATCH_GAP:
            status_ = "watch"
            message = (f"Vigilancia: la precisión en vivo ({realized_accuracy:.0%}) cae "
                       f"{abs(gap):.0%} respecto a lo esperado. Seguir de cerca.")
        else:
            status_ = "ok"
            message = (f"Estable: la precisión en vivo ({realized_accuracy:.0%}) está en línea "
                       f"con lo prometido fuera de muestra.")

        # Serie temporal: precisión por ventanas iguales de resoluciones (orden cronológico).
        series = []
        if n:
            size = max(1, -(-n // max(1, buckets)))  # ceil division
            for i in range(0, n, size):
                chunk = resolved[i:i + size]
                c = sum(1 for r in chunk if r["status"] == "correct")
                series.append({
                    "from": chunk[0]["resolved_at"].isoformat(),
                    "to": chunk[-1]["resolved_at"].isoformat(),
                    "n": len(chunk),
                    "accuracy": round(c / len(chunk), 4),
                })

        # Precisión realizada por activo (¿en qué mercados funciona el modelo?).
        by_asset: dict = {}
        for r in resolved:
            sym = r["asset_symbol"]
            agg = by_asset.setdefault(sym, {"n": 0, "correct": 0})
            agg["n"] += 1
            agg["correct"] += int(r["status"] == "correct")
        by_asset = {
            sym: {"n": a["n"], "accuracy": round(a["correct"] / a["n"], 4)}
            for sym, a in sorted(by_asset.items(), key=lambda kv: kv[1]["n"], reverse=True)
        }

        return {
            "status": status_,
            "message": message,
            "expected_accuracy": expected_accuracy,
            "realized_accuracy": realized_accuracy,
            "gap": gap,
            "n_resolved": n,
            "min_sample": self._MIN_RESOLVED,
            "series": series,
            "by_asset": by_asset,
            "thresholds": {"watch": self._WATCH_GAP, "drift": self._DRIFT_GAP},
        }
