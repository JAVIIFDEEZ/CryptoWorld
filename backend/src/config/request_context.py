"""
config/request_context.py — Contexto de la petición en curso.

Guarda el identificador de correlación en un `ContextVar`, que es lo
correcto aquí y no una variable global: cada hilo de Gunicorn y cada
tarea asíncrona obtienen su propia copia, sin fugas entre peticiones
concurrentes.

Lo usan el middleware (que lo fija), el filtro de logging (que lo lee) y
el manejador de excepciones (que lo devuelve al cliente para que un
usuario pueda citar el identificador al reportar un error).
"""

from contextvars import ContextVar
from typing import Optional

_request_id: ContextVar[Optional[str]] = ContextVar("cryptoworld_request_id", default=None)


def set_request_id(value: Optional[str]) -> object:
    """Fijar el identificador de la petición. Devuelve el token de reseteo."""
    return _request_id.set(value)


def get_request_id() -> Optional[str]:
    """Identificador de la petición en curso, o None fuera de una petición."""
    return _request_id.get()


def reset_request_id(token: object) -> None:
    """Restaurar el valor anterior una vez terminada la petición."""
    _request_id.reset(token)  # type: ignore[arg-type]
