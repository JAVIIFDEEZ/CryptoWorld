"""
application/services/audit.py — Servicio de registro de auditoría.

Punto único por el que pasan todos los eventos de seguridad. Escribe en
dos destinos complementarios:

  - La tabla `audit_log`, consultable y con retención definida, que es la
    evidencia que pide una revisión de cumplimiento.
  - El logger `cryptoworld.audit`, que llega al agregador de logs en
    tiempo real para alertado (por ejemplo, ráfagas de `login.failure`).

Regla de oro: **auditar nunca puede romper la operación auditada**. Si la
escritura falla, se registra el fallo y se continúa; un problema con la
tabla de auditoría no debe impedir que un usuario cambie su contraseña.
"""

import logging
from typing import Optional

from core.infrastructure.persistence.models import AuditLog

logger = logging.getLogger("cryptoworld.audit")

# Cabeceras de proxy en orden de preferencia. `X-Forwarded-For` acumula
# la cadena de proxies; el cliente real es el primer elemento.
_FORWARDED_HEADER = "HTTP_X_FORWARDED_FOR"
_REAL_IP_HEADER = "HTTP_X_REAL_IP"
_USER_AGENT_MAX = 400


def client_ip(request) -> Optional[str]:
    """
    Dirección IP del cliente teniendo en cuenta el proxy inverso.

    Solo se confía en las cabeceras de proxy porque el despliegue coloca
    a Django siempre detrás de nginx o del router de la plataforma; en
    una exposición directa habría que ignorarlas por falsificables.
    """
    if request is None:
        return None

    forwarded = request.META.get(_FORWARDED_HEADER, "")
    if forwarded:
        candidate = forwarded.split(",")[0].strip()
        if candidate:
            return candidate

    real_ip = request.META.get(_REAL_IP_HEADER, "").strip()
    if real_ip:
        return real_ip

    return request.META.get("REMOTE_ADDR") or None


def record(
    action: str,
    *,
    request=None,
    actor=None,
    actor_email: str = "",
    outcome: str = AuditLog.Outcome.SUCCESS,
    target_type: str = "",
    target_id: str = "",
    **metadata,
) -> Optional[AuditLog]:
    """
    Registrar un evento de auditoría.

    Args:
        action: uno de `AuditLog.Action`.
        request: petición HTTP, de la que se extraen IP, user-agent y request-id.
        actor: usuario que ejecuta la acción (None en intentos anónimos).
        actor_email: email a registrar cuando no hay `actor` (login fallido).
        outcome: SUCCESS o FAILURE.
        target_type/target_id: recurso afectado, si lo hay.
        **metadata: contexto adicional no sensible.

    Returns:
        La entrada creada, o None si la escritura falló.
    """
    resolved_actor = actor if _is_persisted_user(actor) else None
    resolved_email = actor_email or (getattr(actor, "email", "") or "")

    ip = client_ip(request)
    user_agent = ""
    request_id = ""
    if request is not None:
        user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:_USER_AGENT_MAX]
        request_id = getattr(request, "request_id", "") or ""

    logger.info(
        "audit %s %s",
        action,
        outcome,
        extra={
            "audit_action": action,
            "audit_outcome": outcome,
            "actor_email": resolved_email or "-",
            "client_ip": ip or "-",
            "target": f"{target_type}:{target_id}" if target_type else "-",
        },
    )

    try:
        return AuditLog.objects.create(
            actor=resolved_actor,
            actor_email=resolved_email[:254],
            action=action,
            outcome=outcome,
            target_type=target_type[:48],
            target_id=str(target_id)[:64],
            ip_address=ip,
            user_agent=user_agent,
            request_id=request_id[:64],
            metadata=metadata or {},
        )
    except Exception:
        # Nunca propagar: la auditoría no puede tumbar la operación.
        logger.exception("No se pudo persistir el evento de auditoría %s", action)
        return None


def _is_persisted_user(actor) -> bool:
    """True si `actor` es un usuario real ya guardado (no AnonymousUser)."""
    return bool(actor is not None and getattr(actor, "pk", None))
