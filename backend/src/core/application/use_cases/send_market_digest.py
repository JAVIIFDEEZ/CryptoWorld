"""
use_cases/send_market_digest.py — Resumen semanal del mercado por email.

Envía a cada usuario suscrito (notify_market_digest=True y email verificado)
un resumen con los mayores movimientos del mercado: top ganadores y
perdedores 24h del catálogo local. Los datos salen de la BD (sincronizada
por Celery), por lo que el envío no consume cuota de APIs externas.

Disparado semanalmente por celery beat (core.tasks.send_market_digest).
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from core.infrastructure.persistence.models import CryptoAsset, User

logger = logging.getLogger(__name__)

_TOP_N = 5


class SendMarketDigestUseCase:
    """Construye y envía el digest de mercado a los usuarios suscritos."""

    def execute(self) -> int:
        """Devuelve el número de emails enviados."""
        recipients = User.objects.filter(
            is_active=True,
            is_email_verified=True,
            notify_market_digest=True,
        )
        if not recipients.exists():
            return 0

        assets = CryptoAsset.objects.filter(
            price_change_24h__isnull=False,
            current_price__gt=0,
        )
        gainers = list(assets.order_by("-price_change_24h")[:_TOP_N])
        losers = list(assets.order_by("price_change_24h")[:_TOP_N])

        if not gainers:
            logger.info("send_market_digest: sin datos de mercado, no se envía nada.")
            return 0

        sent = 0
        for user in recipients:
            context = {
                "username": user.username,
                "gainers": gainers,
                "losers": losers,
                "market_url": f"{settings.FRONTEND_URL}/market",
                "settings_url": f"{settings.FRONTEND_URL}/settings",
            }
            html_body = render_to_string("email/market_digest.html", context)
            text_lines = [
                f"Hola {user.username},",
                "",
                "Resumen del mercado cripto:",
                "",
                "Mayores subidas (24h):",
                *[f"  {a.symbol}: {a.price_change_24h:+.2f}% ({a.current_price} USD)" for a in gainers],
                "",
                "Mayores caídas (24h):",
                *[f"  {a.symbol}: {a.price_change_24h:+.2f}% ({a.current_price} USD)" for a in losers],
                "",
                f"Mercado completo: {settings.FRONTEND_URL}/market",
                "",
                "Puedes darte de baja en Ajustes → Notificaciones.",
            ]

            msg = EmailMultiAlternatives(
                subject="[CryptoWorld] Resumen del mercado",
                body="\n".join(text_lines),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[user.email],
            )
            msg.attach_alternative(html_body, "text/html")
            # Un destinatario fallido no debe abortar el resto del envío
            if msg.send(fail_silently=True):
                sent += 1

        logger.info("send_market_digest: enviados %d de %d", sent, recipients.count())
        return sent
