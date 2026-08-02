"""
logging.py — Formateador JSON para los logs de producción.

Una línea = un objeto JSON. Es lo que esperan los agregadores (Loki, Datadog,
CloudWatch): permite filtrar por `logger`, `level` o cualquier campo extra sin
parsear texto libre. En desarrollo se usa el formato `plain`, más legible.

Los campos `extra` que se pasen al logger se incluyen tal cual, de modo que
`logger.info("orden enviada", extra={"order_id": 7})` sea consultable.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

# Atributos que LogRecord trae de serie: todo lo demás que aparezca en el
# record viene de un `extra=` del llamante y debe emitirse como campo propio.
_STANDARD_ATTRS = frozenset(
    logging.LogRecord("", 0, "", 0, "", None, None).__dict__
) | {"message", "asctime", "taskName"}


class JsonFormatter(logging.Formatter):
    """Serializa cada registro como una línea JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key in _STANDARD_ATTRS or key.startswith("_"):
                continue
            payload[key] = value if isinstance(
                value, (str, int, float, bool, type(None))
            ) else repr(value)

        return json.dumps(payload, ensure_ascii=False, default=str)
