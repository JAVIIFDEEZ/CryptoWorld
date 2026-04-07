"""
interfaces/api/admin_serializers.py — Serializadores para endpoints de administración.

Validan los datos de entrada y serializan las respuestas del panel de admin.
"""

from rest_framework import serializers


# ── Users ──────────────────────────────────────────────────────────

class AdminUserSerializer(serializers.Serializer):
    """Serializa la respuesta de un usuario para el admin."""
    id = serializers.IntegerField()
    email = serializers.EmailField()
    username = serializers.CharField()
    is_active = serializers.BooleanField()
    is_staff = serializers.BooleanField()
    role = serializers.CharField()
    is_email_verified = serializers.BooleanField()
    is_2fa_enabled = serializers.BooleanField()
    date_joined = serializers.CharField()


class AdminUpdateUserSerializer(serializers.Serializer):
    """Valida el cuerpo de PATCH /api/admin/users/<id>/."""
    is_active = serializers.BooleanField(required=False)
    role = serializers.ChoiceField(choices=["user", "admin"], required=False)
    is_email_verified = serializers.BooleanField(required=False)


# ── Assets ─────────────────────────────────────────────────────────

class AdminAssetSerializer(serializers.Serializer):
    """Serializa la respuesta de un activo para el admin."""
    id = serializers.IntegerField()
    symbol = serializers.CharField()
    name = serializers.CharField()
    current_price = serializers.CharField()
    market_cap = serializers.CharField(allow_null=True)
    volume_24h = serializers.CharField(allow_null=True)
    price_change_24h = serializers.CharField(allow_null=True)
    coingecko_id = serializers.CharField(allow_null=True)
    logo_url = serializers.CharField(allow_null=True)


class AdminCreateAssetSerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/admin/assets/."""
    symbol = serializers.CharField(max_length=20)
    name = serializers.CharField(max_length=255)
    current_price = serializers.CharField()
    market_cap = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    volume_24h = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    price_change_24h = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    coingecko_id = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=100)
    logo_url = serializers.URLField(required=False, allow_null=True, allow_blank=True)


class AdminUpdateAssetSerializer(serializers.Serializer):
    """Valida el cuerpo de PATCH /api/admin/assets/<id>/."""
    name = serializers.CharField(max_length=255, required=False)
    current_price = serializers.CharField(required=False)
    market_cap = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    volume_24h = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    price_change_24h = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    coingecko_id = serializers.CharField(required=False, allow_null=True, allow_blank=True, max_length=100)
    logo_url = serializers.URLField(required=False, allow_null=True, allow_blank=True)


# ── Stats ──────────────────────────────────────────────────────────

class AdminStatsSerializer(serializers.Serializer):
    """Serializa estadísticas globales del sistema."""
    total_users = serializers.IntegerField()
    active_users = serializers.IntegerField()
    verified_users = serializers.IntegerField()
    users_with_2fa = serializers.IntegerField()
    admin_users = serializers.IntegerField()
    total_assets = serializers.IntegerField()
    total_analyses = serializers.IntegerField()
