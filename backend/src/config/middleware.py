"""
config/middleware.py — Middleware transversal de la aplicación.

RequestIDMiddleware asigna a cada petición un identificador de
correlación y lo devuelve en la cabecera `X-Request-ID`. Con él, una
incidencia reportada por un usuario ("me ha salido este error") se puede
localizar en los logs sin ambigüedad, que es el requisito práctico de
trazabilidad de cualquier operación auditada.
"""

import uuid

from config.request_context import reset_request_id, set_request_id

# Cabecera de entrada aceptada: si el proxy o el cliente ya generó un
# identificador, se respeta para poder seguir la traza extremo a extremo.
_INBOUND_HEADER = "HTTP_X_REQUEST_ID"
_OUTBOUND_HEADER = "X-Request-ID"
_MAX_LENGTH = 64


class RequestIDMiddleware:
    """Fija un identificador de correlación por petición."""

    def __init__(self, get_response):
        self._get_response = get_response

    def __call__(self, request):
        request_id = _sanitize(request.META.get(_INBOUND_HEADER, "")) or uuid.uuid4().hex
        request.request_id = request_id
        token = set_request_id(request_id)
        try:
            response = self._get_response(request)
        finally:
            reset_request_id(token)
        response[_OUTBOUND_HEADER] = request_id
        return response


def _sanitize(value: str) -> str:
    """
    Aceptar solo identificadores inocuos venidos del exterior.

    El valor acaba en una cabecera de respuesta y en los logs, así que se
    restringe a caracteres seguros y longitud acotada para que nadie
    pueda inyectar contenido a través de él.
    """
    cleaned = "".join(c for c in value.strip() if c.isalnum() or c in "-_")
    return cleaned[:_MAX_LENGTH]
