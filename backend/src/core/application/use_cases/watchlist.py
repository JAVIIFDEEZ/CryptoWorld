"""
watchlist.py — Vigilancia de direcciones on-chain (whale tracking ligero).

Un usuario añade direcciones de interés (ballenas, tesorerías, contratos) a su
watchlist. Una tarea periódica consulta el saldo nativo de cada una vía Blockscout
y, cuando varía por encima del umbral configurado, registra una alerta y
(opcionalmente) avisa por email. Es vigilancia on-chain real sin construir un
indexador propio.

Buenas prácticas:
  · El saldo se compara contra el último conocido (delta con etiqueta diferida).
  · El umbral es por dirección, así una ballena con mucho movimiento no inunda
    de alertas y una tesorería estable avisa de cualquier cambio relevante.
  · La consulta de red nunca rompe la pasada: un fallo en una dirección se omite.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_NATIVE_DECIMALS = 18


def _to_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _native_balance(info: dict) -> float:
    return _to_float(info.get("coin_balance")) / (10 ** _NATIVE_DECIMALS)


def _serialize_watch(w) -> dict:
    return {
        "id": w.id,
        "chain": w.chain,
        "address": w.address,
        "label": w.label or None,
        "native_symbol": w.native_symbol or None,
        "alert_threshold_pct": w.alert_threshold_pct,
        "last_balance": round(w.last_balance, 8) if w.last_balance is not None else None,
        "last_value_usd": round(w.last_value_usd, 2) if w.last_value_usd is not None else None,
        "last_checked_at": w.last_checked_at.isoformat() if w.last_checked_at else None,
        "created_at": w.created_at.isoformat(),
    }


class AddWatchedAddressUseCase:
    """Añade una dirección a la watchlist del usuario, con su saldo inicial."""

    def __init__(self, client=None) -> None:
        from core.infrastructure.external_apis.blockscout_client import BlockscoutClient
        self._client = client or BlockscoutClient()

    def execute(self, owner, chain: str, address: str, label: str = "",
                threshold_pct: float = 5.0) -> dict:
        from django.utils import timezone
        from core.infrastructure.external_apis.blockscout_client import (
            CHAINS, SUPPORTED_CHAINS, BlockscoutClientError, is_valid_address,
        )
        from core.infrastructure.persistence.models import WatchedAddress

        chain = (chain or "").strip().lower()
        address = (address or "").strip()
        if chain not in SUPPORTED_CHAINS:
            return {"error": f"Red '{chain}' no soportada. Disponibles: {SUPPORTED_CHAINS}"}
        if not is_valid_address(address):
            return {"error": "Dirección inválida: debe ser 0x seguido de 40 caracteres hexadecimales."}

        if WatchedAddress.objects.filter(owner=owner, chain=chain, address__iexact=address).exists():
            return {"error": "Esa dirección ya está en tu watchlist para esta red."}

        threshold_pct = min(max(_to_float(threshold_pct, 5.0), 0.1), 100.0)
        meta = CHAINS[chain]

        # Saldo inicial (best-effort: si la red falla, se crea sin saldo y la tarea
        # lo rellenará en la siguiente pasada).
        balance = value_usd = None
        try:
            info = self._client.get_address(chain, address)
            balance = round(_native_balance(info), 8)
            price = _to_float(info.get("exchange_rate"))
            value_usd = round(balance * price, 2) if price else None
        except BlockscoutClientError as exc:
            logger.warning("add_watched %s/%s saldo inicial falló: %s", chain, address, exc)

        watch = WatchedAddress.objects.create(
            owner=owner, chain=chain, address=address, label=(label or "").strip()[:80],
            native_symbol=meta["native"], alert_threshold_pct=threshold_pct,
            last_balance=balance, last_value_usd=value_usd,
            last_checked_at=timezone.now() if balance is not None else None,
        )
        return _serialize_watch(watch)


class RemoveWatchedAddressUseCase:
    """Elimina una dirección de la watchlist del usuario."""

    def execute(self, owner, watch_id: int) -> dict:
        from core.infrastructure.persistence.models import WatchedAddress

        watch = WatchedAddress.objects.filter(id=watch_id, owner=owner).first()
        if watch is None:
            return {"error": "No encontrada."}
        watch.delete()
        return {"id": watch_id, "removed": True}


class WatchlistUseCase:
    """Watchlist del usuario con el saldo de cada dirección y alertas recientes."""

    def execute(self, owner, alerts_limit: int = 20) -> dict:
        from core.infrastructure.persistence.models import AddressAlert, WatchedAddress

        watched = WatchedAddress.objects.filter(owner=owner)
        alerts = (
            AddressAlert.objects.select_related("watched")
            .filter(owner=owner).order_by("-created_at")[:alerts_limit]
        )
        return {
            "count": watched.count(),
            "results": [_serialize_watch(w) for w in watched],
            "alerts": [
                {
                    "id": a.id,
                    "watched_id": a.watched_id,
                    "chain": a.watched.chain,
                    "address": a.watched.address,
                    "label": a.watched.label or None,
                    "direction": a.direction,
                    "delta": round(a.delta, 8),
                    "delta_pct": round(a.delta_pct, 4),
                    "balance_after": round(a.balance_after, 8),
                    "value_usd": a.value_usd,
                    "created_at": a.created_at.isoformat(),
                }
                for a in alerts
            ],
        }


class MonitorWatchedAddressesUseCase:
    """Revisa las direcciones vigiladas y crea alertas ante movimientos grandes."""

    def __init__(self, client=None) -> None:
        from core.infrastructure.external_apis.blockscout_client import BlockscoutClient
        self._client = client or BlockscoutClient()

    def execute(self) -> dict:
        from django.utils import timezone
        from core.infrastructure.external_apis.blockscout_client import BlockscoutClientError
        from core.infrastructure.persistence.models import AddressAlert, WatchedAddress

        checked = alerts_created = 0
        for watch in WatchedAddress.objects.select_related("owner").all():
            try:
                info = self._client.get_address(watch.chain, watch.address)
            except BlockscoutClientError as exc:
                logger.warning("monitor_watched %s/%s: %s", watch.chain, watch.address, exc)
                continue

            balance = _native_balance(info)
            price = _to_float(info.get("exchange_rate"))
            value_usd = round(balance * price, 2) if price else None
            checked += 1

            prev = watch.last_balance
            if prev is not None and prev > 0:
                delta = balance - prev
                delta_pct = (delta / prev) * 100.0
                if abs(delta_pct) >= watch.alert_threshold_pct and abs(delta) > 0:
                    AddressAlert.objects.create(
                        watched=watch, owner=watch.owner,
                        direction="increase" if delta > 0 else "decrease",
                        balance_before=prev, balance_after=balance,
                        delta=delta, delta_pct=round(delta_pct, 4),
                        value_usd=round(abs(delta) * price, 2) if price else None,
                        notified=self._notify(watch, delta, delta_pct, price),
                    )
                    alerts_created += 1

            watch.last_balance = balance
            watch.last_value_usd = value_usd
            watch.last_checked_at = timezone.now()
            watch.save(update_fields=["last_balance", "last_value_usd", "last_checked_at", "updated_at"])

        logger.info("monitor_watched: %d revisadas, %d alertas", checked, alerts_created)
        return {"checked": checked, "alerts": alerts_created}

    @staticmethod
    def _notify(watch, delta, delta_pct, price) -> bool:
        """Email opcional al dueño ante un movimiento. Degradación silenciosa."""
        from django.conf import settings
        from django.core.mail import EmailMultiAlternatives

        owner = watch.owner
        if owner is None or not owner.email:
            return False
        verb = "entrada" if delta > 0 else "salida"
        name = watch.label or watch.address
        body = (
            f"Hola {owner.username},\n\n"
            f"Movimiento detectado en una dirección que vigilas ({watch.chain}):\n"
            f"{name}\n\n"
            f"Variación de saldo: {delta_pct:+.1f}% ({verb} de {abs(delta):.4f} {watch.native_symbol}).\n\n"
            f"Esta notificación es informativa y no constituye asesoramiento financiero.\n\n"
            f"— CryptoWorld"
        )
        try:
            EmailMultiAlternatives(
                subject=f"[CryptoWorld] Movimiento on-chain · {name[:24]}",
                body=body, from_email=settings.DEFAULT_FROM_EMAIL, to=[owner.email],
            ).send(fail_silently=True)
            return True
        except Exception as exc:  # noqa: BLE001 — la vigilancia no debe romper por email
            logger.warning("monitor_watched notificación falló: %s", exc)
            return False
