"""
use_cases/send_risk_digest.py — Resumen diario del riesgo de cartera por email.

Para cada usuario suscrito (notify_risk_digest=True y email verificado) con
exposición abierta, calcula su riesgo con PortfolioRiskUseCase y le envía un
resumen: exposición bruta/neta, VaR/CVaR, concentración, estado de las barreras
del OMS y P&L realizado hoy. Reutiliza toda la matemática del módulo de riesgo
(#3) — el email es solo el canal.

Disparado a diario por celery beat (core.tasks.send_risk_digest).
"""

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


class SendRiskDigestUseCase:
    """Construye y envía el digest de riesgo a los usuarios suscritos."""

    def execute(self) -> int:
        from core.application.use_cases.paper_trading import daily_live_realized_pnl
        from core.application.use_cases.portfolio_risk import PortfolioRiskUseCase
        from core.infrastructure.persistence.models import LiveRiskPolicy, User

        recipients = User.objects.filter(
            is_active=True, is_email_verified=True, notify_risk_digest=True,
        )
        sent = 0
        for user in recipients:
            try:
                risk = PortfolioRiskUseCase().execute(user)
                if risk.get("status") != "OK":
                    continue     # sin exposición: no se envía nada
                policy = LiveRiskPolicy.objects.filter(owner=user).first()
                var = risk.get("var") or {}
                context = {
                    "username": user.username,
                    "gross_usd": risk["gross_usd"],
                    "net_usd": risk["net_usd"],
                    "top_concentration_pct": risk.get("top_concentration_pct", 0.0),
                    "var95": var.get("var95_usd"),
                    "cvar95": var.get("cvar95_usd"),
                    "worst_day": var.get("worst_day_usd"),
                    "var_status": var.get("status"),
                    "exposures": risk["exposures"][:8],
                    "daily_loss_limit": policy.daily_loss_limit_usd if policy else None,
                    "max_concentration_pct": policy.max_concentration_pct if policy else None,
                    "realized_today": daily_live_realized_pnl(user),
                    "portfolio_url": f"{settings.FRONTEND_URL}/portfolio",
                    "settings_url": f"{settings.FRONTEND_URL}/settings",
                }
                if self._send(user, context):
                    sent += 1
            except Exception as exc:  # noqa: BLE001 — un usuario no frena el resto
                logger.warning("send_risk_digest %s falló: %s", user.id, exc)
        logger.info("send_risk_digest: %d emails enviados", sent)
        return sent

    @staticmethod
    def _send(user, ctx: dict) -> bool:
        try:
            html_body = render_to_string("email/risk_digest.html", ctx)
        except Exception:  # noqa: BLE001 — plantilla ausente: usa solo texto
            html_body = None
        var_line = (f"VaR 95%: {ctx['var95']} USD · CVaR 95%: {ctx['cvar95']} USD · "
                    f"peor día visto: {ctx['worst_day']} USD"
                    if ctx["var_status"] == "OK" else "VaR: histórico insuficiente")
        text = "\n".join([
            f"Hola {ctx['username']},", "",
            "Resumen diario de riesgo de tu cartera:", "",
            f"Exposición bruta: {ctx['gross_usd']} USD · neta: {ctx['net_usd']} USD",
            f"Concentración del mayor activo: {ctx['top_concentration_pct']}%",
            var_line, "",
            f"P&L realizado hoy (ejecución real): {ctx['realized_today']} USD",
            (f"Límite de pérdida diaria: {ctx['daily_loss_limit']} USD"
             if ctx["daily_loss_limit"] else "Sin límite de pérdida diaria configurado"),
            (f"Límite de concentración: {ctx['max_concentration_pct']}%"
             if ctx["max_concentration_pct"] else "Sin límite de concentración configurado"),
            "",
            f"Cartera: {ctx['portfolio_url']}",
            "Puedes darte de baja en Ajustes → Notificaciones.",
        ])
        msg = EmailMultiAlternatives(
            subject="[CryptoWorld] Resumen diario de riesgo",
            body=text, from_email=settings.DEFAULT_FROM_EMAIL, to=[user.email],
        )
        if html_body:
            msg.attach_alternative(html_body, "text/html")
        return bool(msg.send(fail_silently=True))
