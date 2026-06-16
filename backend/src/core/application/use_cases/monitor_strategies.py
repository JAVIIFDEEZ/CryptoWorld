"""
monitor_strategies.py — Señales en vivo de estrategias generadas (Módulo 2).

"Activar" una estrategia generada la pone en monitorización: una tarea periódica
reevalúa su señal sobre los datos más recientes y, cuando pasa a compra o venta,
notifica por email a su dueño. Conecta el generador con el flujo operativo
(alertas), sin construir un motor de trading: solo evalúa la señal causal en la
última vela vía signal_state (Módulo 0).
"""

import logging

from core.domain.services.strategy_spec import describe_spec, signal_state

logger = logging.getLogger(__name__)

# Velas suficientes para calentar los indicadores más lentos del spec.
_SIGNAL_LIMIT = 200


class StrategySignalUseCase:
    """Calcula la señal actual (BUY/SELL/HOLD) de una estrategia bajo demanda."""

    def execute(self, strategy_id: int) -> dict:
        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
        from core.infrastructure.persistence.models import StrategyDefinition

        obj = StrategyDefinition.objects.select_related("asset").filter(id=strategy_id).first()
        if obj is None:
            return {"error": "Estrategia no encontrada."}
        symbol = obj.asset.symbol if obj.asset else None
        if not symbol:
            return {"error": "La estrategia no tiene activo asociado."}

        res = fetch_ohlcv_dataframe(symbol=symbol, interval=obj.interval, limit=_SIGNAL_LIMIT)
        if res is None or res.df.empty:
            return {"error": f"No hay datos de mercado para {symbol}."}

        state = signal_state(res.df, obj.spec)
        last_ts = res.df["timestamp"].iloc[-1] if "timestamp" in res.df.columns else None
        return {
            "strategy_id": obj.id,
            "asset_symbol": symbol,
            "interval": obj.interval,
            "description": describe_spec(obj.spec),
            "as_of_ts": int(last_ts) if last_ts is not None else None,
            **state,
        }


class EvaluateMonitoredStrategiesUseCase:
    """
    Reevalúa todas las estrategias monitorizadas y notifica los cambios de señal.
    Pensada para ejecutarse periódicamente (Celery beat). Solo notifica cuando la
    señal cambia respecto a la anterior y es accionable (BUY o SELL).
    """

    def execute(self) -> dict:
        from django.utils import timezone
        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
        from core.infrastructure.persistence.models import StrategyDefinition, StrategySignalEvent

        monitored = StrategyDefinition.objects.select_related("asset", "owner").filter(is_monitored=True)
        evaluated = 0
        notified = 0
        for obj in monitored:
            symbol = obj.asset.symbol if obj.asset else None
            if not symbol:
                continue
            res = fetch_ohlcv_dataframe(symbol=symbol, interval=obj.interval, limit=_SIGNAL_LIMIT)
            if res is None or res.df.empty:
                continue
            evaluated += 1
            new_signal = signal_state(res.df, obj.spec)["signal"]
            previous = obj.last_signal
            obj.last_signal = new_signal
            obj.last_signal_at = timezone.now()
            obj.save(update_fields=["last_signal", "last_signal_at", "updated_at"])

            if new_signal != previous and new_signal in ("BUY", "SELL"):
                price = float(res.df["close"].iloc[-1])
                sent = self._notify(obj, new_signal)
                StrategySignalEvent.objects.create(
                    strategy=obj, owner=obj.owner, signal=new_signal, price=price, notified=sent,
                )
                if sent:
                    notified += 1

        logger.info("monitor_strategies: %d evaluadas, %d notificadas", evaluated, notified)
        return {"evaluated": evaluated, "notified": notified}

    @staticmethod
    def _notify(obj, signal: str) -> bool:
        """Envía un email al dueño con el cambio de señal. Degradación silenciosa."""
        from django.conf import settings
        from django.core.mail import EmailMultiAlternatives

        owner = obj.owner
        if owner is None or not owner.email:
            return False
        verb = "COMPRA" if signal == "BUY" else "VENTA"
        symbol = obj.asset.symbol if obj.asset else "—"
        body = (
            f"Hola {owner.username},\n\n"
            f"Tu estrategia monitorizada sobre {symbol} ({obj.interval}) ha emitido una "
            f"señal de {verb}.\n\n"
            f"Estrategia: {describe_spec(obj.spec)}\n\n"
            f"Esta notificación es informativa y no constituye asesoramiento financiero.\n\n"
            f"— CryptoWorld"
        )
        try:
            msg = EmailMultiAlternatives(
                subject=f"[CryptoWorld] Señal de {verb} · {symbol}",
                body=body,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[owner.email],
            )
            msg.send(fail_silently=True)
            return True
        except Exception as exc:  # noqa: BLE001 — la monitorización no debe romper por email
            logger.warning("monitor_strategies: fallo notificando %s: %s", obj.id, exc)
            return False
