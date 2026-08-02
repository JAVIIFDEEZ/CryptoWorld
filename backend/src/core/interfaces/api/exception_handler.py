"""
interfaces/api/exception_handler.py — Contrato de error único de la API.

Antes de esta pieza cada view improvisaba su forma de error: unas
devolvían `{"error": "..."}`, otras `{"detail": "..."}` y otras el dict
crudo del serializer. Además, cualquier excepción no prevista (un
timeout de Binance, un fallo de CoinGecko) salía como una página HTML de
error 500 de Django, imposible de consumir por el cliente.

Aquí se normaliza todo a una única envolvente:

    {
      "error": {
        "code": "validation_error",
        "message": "Los datos enviados no son válidos.",
        "details": {"email": ["Introduzca una dirección de correo válida."]}
      },
      "request_id": "3f2a…"
    }

`request_id` permite correlacionar el error que ve el usuario con la
traza completa en los logs del servidor, sin filtrarle nada del interior.
"""

import logging

from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from config.request_context import get_request_id

logger = logging.getLogger(__name__)


class DomainError(Exception):
    """
    Error de negocio con código estable.

    Los casos de uso lanzan `ValueError` para las reglas de dominio; esta
    excepción es la versión enriquecida para cuando el cliente necesita
    distinguir programáticamente el motivo (por ejemplo, para mostrar un
    aviso distinto según el código).
    """

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "domain_error"

    def __init__(self, message: str, code: str = "", status_code: int = 0) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.default_code
        if status_code:
            self.status_code = status_code


class ExternalServiceError(DomainError):
    """Una API externa (Binance, CoinGecko, Blockchair…) no ha respondido."""

    status_code = status.HTTP_502_BAD_GATEWAY
    default_code = "external_service_unavailable"


# Códigos de error por clase de excepción de DRF. Se exponen al cliente
# como identificadores estables: la redacción del mensaje puede cambiar,
# el código no.
_DRF_CODES = {
    exceptions.ParseError: "malformed_request",
    exceptions.AuthenticationFailed: "authentication_failed",
    exceptions.NotAuthenticated: "not_authenticated",
    exceptions.PermissionDenied: "permission_denied",
    exceptions.NotFound: "not_found",
    exceptions.MethodNotAllowed: "method_not_allowed",
    exceptions.NotAcceptable: "not_acceptable",
    exceptions.UnsupportedMediaType: "unsupported_media_type",
    exceptions.Throttled: "rate_limit_exceeded",
    exceptions.ValidationError: "validation_error",
}

_GENERIC_MESSAGES = {
    status.HTTP_400_BAD_REQUEST: "La petición no es válida.",
    status.HTTP_401_UNAUTHORIZED: "Autenticación requerida.",
    status.HTTP_403_FORBIDDEN: "No tienes permiso para realizar esta acción.",
    status.HTTP_404_NOT_FOUND: "El recurso solicitado no existe.",
    status.HTTP_429_TOO_MANY_REQUESTS: "Has excedido el límite de peticiones. Inténtalo más tarde.",
    status.HTTP_500_INTERNAL_SERVER_ERROR: "Se ha producido un error interno.",
}


def api_exception_handler(exc, context):
    """
    Manejador de excepciones global de DRF (`EXCEPTION_HANDLER`).

    Traduce cualquier excepción a la envolvente de error estándar. Las
    excepciones no previstas se registran con traza completa y se
    devuelven como 500 genérico: el detalle interno nunca viaja al
    cliente, ni siquiera con DEBUG activo, porque el mismo código sirve
    a producción.
    """
    # Excepciones de Django que DRF ya sabe traducir a las suyas.
    if isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()
    elif isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(exc.messages)

    if isinstance(exc, DomainError):
        return _build_response(exc.status_code, exc.code, exc.message)

    if isinstance(exc, ValueError):
        # Convención del proyecto: los casos de uso señalan violaciones de
        # regla de negocio con ValueError y un mensaje ya apto para el
        # usuario final.
        return _build_response(
            status.HTTP_400_BAD_REQUEST, "domain_error", str(exc)
        )

    response = drf_exception_handler(exc, context)

    if response is None:
        # Excepción no controlada: se registra entera y se devuelve un 500
        # opaco. Es el único punto donde la API puede producir un 500.
        view = context.get("view")
        request = context.get("request")
        logger.exception(
            "Excepción no controlada en %s",
            view.__class__.__name__ if view else "vista desconocida",
            extra={
                "path": getattr(request, "path", None),
                "method": getattr(request, "method", None),
            },
        )
        return _build_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "internal_error",
            _GENERIC_MESSAGES[status.HTTP_500_INTERNAL_SERVER_ERROR],
        )

    code = _code_for(exc)
    message, details = _split_detail(response.data, response.status_code)

    extra_headers = {
        key: value
        for key, value in response.items()
        # `Retry-After` en un 429 es información operativa útil que hay
        # que conservar al reconstruir la respuesta.
        if key.lower() == "retry-after"
    }
    return _build_response(
        response.status_code, code, message, details, headers=extra_headers
    )


def _code_for(exc) -> str:
    for exc_class, code in _DRF_CODES.items():
        if isinstance(exc, exc_class):
            return code
    detail_code = getattr(getattr(exc, "detail", None), "code", None)
    return str(detail_code) if detail_code else "error"


def _split_detail(data, status_code: int):
    """
    Separar el mensaje legible de los detalles campo a campo.

    DRF entrega `{"detail": "..."}` para los errores simples y un dict
    campo → [errores] para los de validación; se normalizan ambos.
    """
    generic = _GENERIC_MESSAGES.get(status_code, "La petición no se ha podido completar.")

    if isinstance(data, dict):
        if "detail" in data and len(data) == 1:
            return str(data["detail"]), None
        return generic, data
    if isinstance(data, list):
        return generic, {"non_field_errors": data}
    if data is None:
        return generic, None
    return str(data), None


def _build_response(status_code: int, code: str, message: str, details=None, headers=None):
    body = {
        "error": {
            "code": code,
            "message": message,
        },
        "request_id": get_request_id() or "-",
    }
    if details:
        body["error"]["details"] = details
    return Response(body, status=status_code, headers=headers or None)
