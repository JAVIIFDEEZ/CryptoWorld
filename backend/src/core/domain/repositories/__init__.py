"""
domain/repositories/__init__.py

Los repositorios del dominio son INTERFACES ABSTRACTAS (contratos).
Definen QUÉ operaciones de persistencia necesita el dominio,
pero NO CÓMO se implementan.

La implementación concreta vive en infrastructure/persistence/.

Este patrón es la Inversión de Dependencias (DIP) de SOLID:
el dominio no depende de la infraestructura; la infraestructura
implementa los contratos del dominio.
"""
