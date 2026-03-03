"""
domain/services/__init__.py

Los servicios de dominio contienen lógica de negocio que NO pertenece
naturalmente a ninguna entidad concreta sino que involucra
coordinación entre varias entidades o reglas transversales.

Ejemplo: validar que no exista ya un usuario con ese email
requiere consultar el repositorio, lo que una entidad no puede hacer.
"""
