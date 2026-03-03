"""
domain/value_objects/__init__.py

Los Value Objects son objetos inmutables que se identifican
por su VALOR, no por una identidad única (a diferencia de las entidades).

Ejemplo: Email("user@example.com") es igual a otro Email("user@example.com")
sin importar dónde viva en memoria.

Se usan para encapsular validaciones y semántica dentro del dominio.
"""
