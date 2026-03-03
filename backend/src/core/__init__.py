"""
core/__init__.py

La app 'core' agrupa toda la lógica del sistema siguiendo
Clean Architecture. Internamente se divide en cuatro capas:

  domain/         ← Reglas de negocio puras (sin frameworks)
  application/    ← Casos de uso que orquestan el dominio
  infrastructure/ ← Adaptadores externos (ORM, APIs externas)
  interfaces/     ← Controladores HTTP (DRF views, serializers)

La dirección de dependencias es siempre hacia adentro:
  interfaces → application → domain
  infrastructure implementa contratos del domain
"""
