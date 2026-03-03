"""
interfaces/__init__.py

La capa de interfaces contiene los controladores HTTP.
Es la única capa que conoce el protocolo HTTP y los formatos JSON.

Depende de la capa de aplicación (casos de uso) para ejecutar acciones.
Nunca accede directamente al dominio ni a la infraestructura.
"""
