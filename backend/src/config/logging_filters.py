"""
config/logging_filters.py — Soporte de logging estructurado.

Contiene dos piezas que `LOGGING` (settings.py) referencia:

  - RequestIDFilter: inyecta en cada registro el identificador de
    correlación de la petición en curso, de forma que todas las líneas
    de una misma petición puedan agruparse en el agregador de logs.
  - JSONFormatter: serializa el registro a una línea JSON, el formato
    que consumen los agregadores (Railway, CloudWatch, Loki, Datadog).

No depende de librerías externas: un formateador JSON son treinta líneas
y evita añadir una dependencia más a la superficie de suministro.
"""

import json
import logging

from config.request_context import get_request_id

# Atributos que `logging` pone en todo LogRecord y que no aportan nada al
# JSON final; cualquier clave fuera de esta lista es un campo extra que el
# emisor añadió con `logger.info(..., extra={...})` y sí se serializa.
_RESERVED_ATTRS = frozenset(
    {
        "args", "asctime", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "module", "msecs",
        "message", "msg", "name", "pathname", "process", "processName",
        "relativeCreated", "stack_info", "taskName", "thread", "threadName",
        "request_id",
    }
)


class RequestIDFilter(logging.Filter):
    """Añade el atributo `request_id` a todos los registros."""

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = get_request_id() or "-"
        return True


class JSONFormatter(logging.Formatter):
    """Formatea cada registro como una única línea JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or get_request_id() or "-",
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        # Campos añadidos por quien emite el log con extra={...}
        for key, value in record.__dict__.items():
            if key in _RESERVED_ATTRS or key.startswith("_"):
                continue
            payload[key] = value if _is_json_safe(value) else repr(value)

        return json.dumps(payload, ensure_ascii=False, default=str)


def _is_json_safe(value: object) -> bool:
    return isinstance(value, (str, int, float, bool, type(None), list, dict))
