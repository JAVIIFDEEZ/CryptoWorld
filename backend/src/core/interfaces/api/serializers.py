"""
interfaces/api/serializers.py — Serializadores DRF.

Los serializadores son el contrato entre el JSON que llega/sale por HTTP
y los datos que entiende la aplicación.

Su responsabilidad:
  - Validar campos de entrada (formato, required, etc.)
  - Transformar JSON → datos Python para los DTOs
  - Transformar datos Python → JSON de respuesta

NO contienen lógica de negocio. Eso vive en los casos de uso.
"""

from rest_framework import serializers


# ── Auth ───────────────────────────────────────────────────────────

class RegisterSerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/auth/register."""
    email = serializers.EmailField()
    username = serializers.CharField(min_length=3, max_length=150)
    password = serializers.CharField(
        min_length=8,
        write_only=True,
        style={"input_type": "password"},
    )
    password_confirm = serializers.CharField(
        write_only=True,
        style={"input_type": "password"},
    )

    def validate(self, data: dict) -> dict:
        """Validación cruzada: las dos contraseñas deben coincidir."""
        if data["password"] != data["password_confirm"]:
            raise serializers.ValidationError(
                {"password_confirm": "Las contraseñas no coinciden."}
            )
        return data


class LoginSerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/auth/login."""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


# ── Assets ─────────────────────────────────────────────────────────

class CryptoAssetSerializer(serializers.Serializer):
    """Serializa la respuesta de GET /api/assets."""
    id = serializers.IntegerField()
    symbol = serializers.CharField()
    name = serializers.CharField()
    current_price = serializers.CharField()
    market_cap = serializers.CharField(allow_null=True)
    volume_24h = serializers.CharField(allow_null=True)
    price_change_24h = serializers.CharField(allow_null=True)
    is_bullish_24h = serializers.BooleanField()


# ── Analysis ───────────────────────────────────────────────────────

class AnalysisRequestSerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/analysis/run."""
    asset_symbol = serializers.CharField(max_length=20)
    analysis_type = serializers.ChoiceField(
        choices=["RSI", "MACD", "SMA", "EMA", "BOLLINGER"],
    )


class AnalysisOutputSerializer(serializers.Serializer):
    """Serializa la respuesta de POST /api/analysis/run."""
    id = serializers.IntegerField()
    asset_symbol = serializers.CharField()
    analysis_type = serializers.CharField()
    status = serializers.CharField()
    result = serializers.DictField(allow_null=True)
