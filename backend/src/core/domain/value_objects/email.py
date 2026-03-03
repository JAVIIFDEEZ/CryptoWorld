"""
email.py — Value Object: Email.

Encapsula la validación y representación de un email.
Al ser un Value Object:
  - Es inmutable (frozen=True)
  - Se compara por valor, no por referencia
  - Encapsula la regla de validación de formato

Principio aplicado: Encapsulación y semántica de dominio.
En lugar de usar strings crudos, el dominio usa tipos con significado.
"""

import re
from dataclasses import dataclass


# Expresión regular básica para validar formato de email
_EMAIL_REGEX = re.compile(r"^[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}$")


@dataclass(frozen=True)
class Email:
    """
    Value Object que representa una dirección de email válida.

    Al ser frozen=True, es inmutable: no se puede modificar tras creación.
    Esto garantiza consistencia y permite usarlo como clave de diccionario.
    """
    value: str

    def __post_init__(self) -> None:
        if not _EMAIL_REGEX.match(self.value):
            raise ValueError(f"Formato de email inválido: '{self.value}'")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class CryptoSymbol:
    """
    Value Object que representa el ticker de un criptoactivo.
    Siempre se almacena en mayúsculas.
    """
    value: str

    def __post_init__(self) -> None:
        # Forzar mayúsculas; dataclass frozen no permite asignación directa
        object.__setattr__(self, "value", self.value.upper())
        if not self.value or not self.value.isalpha():
            raise ValueError(f"Símbolo de criptoactivo inválido: '{self.value}'")

    def __str__(self) -> str:
        return self.value
