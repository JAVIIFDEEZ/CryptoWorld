"""
application/dto/__init__.py

Los DTOs (Data Transfer Objects) son estructuras simples que
transportan datos entre la capa de interfaces (HTTP) y la de aplicación.

Son fundamentales para mantener la separación entre:
- Lo que el cliente HTTP envía (JSON)
- Lo que el dominio entiende (entidades)

Ventaja: si cambia la API REST, solo cambian los DTOs, no el dominio.
"""
