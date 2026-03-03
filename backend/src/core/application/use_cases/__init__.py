"""
application/use_cases/__init__.py

Los casos de uso (Use Cases / Interactors) son el corazón de la capa de aplicación.
Cada uno representa una sola intención del usuario del sistema.

Responsabilidad: orquestar entidades, repositorios y servicios de dominio
para cumplir un objetivo de negocio concreto.

Regla de oro: un caso de uso NO sabe de HTTP, NO sabe de Django,
NO sabe de bases de datos. Solo habla el lenguaje del dominio.
"""
