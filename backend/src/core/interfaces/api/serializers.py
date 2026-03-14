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


class LogoutSerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/auth/logout/."""
    refresh_token = serializers.CharField()


class VerifyEmailSerializer(serializers.Serializer):
    """Valida los query params de GET /api/auth/verify-email/."""
    token = serializers.CharField()


class PasswordResetRequestSerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/auth/password-reset/."""
    email = serializers.EmailField()


class PasswordResetConfirmSerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/auth/password-reset/confirm/."""
    uid = serializers.CharField()
    token = serializers.CharField()
    new_password = serializers.CharField(min_length=8, write_only=True)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, data: dict) -> dict:
        if data["new_password"] != data["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Las contraseñas no coinciden."}
            )
        return data


class ChangePasswordSerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/auth/change-password/."""
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(min_length=8, write_only=True)
    new_password_confirm = serializers.CharField(write_only=True)

    def validate(self, data: dict) -> dict:
        if data["new_password"] != data["new_password_confirm"]:
            raise serializers.ValidationError(
                {"new_password_confirm": "Las contraseñas no coinciden."}
            )
        return data


class Enable2FASerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/auth/2fa/enable/."""
    totp_code = serializers.CharField(min_length=6, max_length=6)


class Disable2FASerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/auth/2fa/disable/."""
    totp_code = serializers.CharField(min_length=6, max_length=6)


class Verify2FALoginSerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/auth/2fa/login/."""
    pre_auth_token = serializers.CharField()
    totp_code = serializers.CharField(min_length=6, max_length=6)


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
    coingecko_id = serializers.CharField(allow_null=True)
    logo_url = serializers.CharField(allow_null=True)
    asset_address = serializers.CharField(allow_null=True)
    decimals = serializers.IntegerField(allow_null=True)
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


# ── Market Intelligence ───────────────────────────────────────────

class MarketOverviewSerializer(serializers.Serializer):
    """Serializa la respuesta de GET /api/market/overview/."""
    total_market_cap_usd = serializers.CharField()
    total_volume_24h_usd = serializers.CharField()
    btc_dominance_pct = serializers.CharField()
    fear_greed_index = serializers.IntegerField(min_value=0, max_value=100)
    updated_at = serializers.CharField()


class OhlcvQuerySerializer(serializers.Serializer):
    """Valida query params de GET /api/assets/<symbol>/ohlcv/."""
    interval = serializers.ChoiceField(
        choices=["1m", "5m", "15m", "1h", "4h", "1d"],
        default="1h",
        required=False,
    )
    limit = serializers.IntegerField(min_value=10, max_value=500, default=120, required=False)


class OhlcvCandleSerializer(serializers.Serializer):
    """Serializa una vela OHLCV."""
    open_time = serializers.CharField()
    open = serializers.CharField()
    high = serializers.CharField()
    low = serializers.CharField()
    close = serializers.CharField()
    volume = serializers.CharField()


class OnChainQuerySerializer(serializers.Serializer):
    """Valida query params de GET /api/blockchain/metrics/."""
    symbol = serializers.CharField(max_length=20, required=False, default="BTC")
    metric = serializers.ChoiceField(
        choices=["active_addresses", "hashrate", "tx_count", "gas_price"],
        required=False,
        default="active_addresses",
    )
    days = serializers.IntegerField(min_value=7, max_value=365, default=30, required=False)


class OnChainMetricPointSerializer(serializers.Serializer):
    """Serializa un punto temporal on-chain."""
    metric = serializers.CharField()
    symbol = serializers.CharField()
    timestamp = serializers.CharField()
    value = serializers.CharField()
    source = serializers.CharField()


class NewsQuerySerializer(serializers.Serializer):
    """Valida query params de GET /api/news/."""
    q = serializers.CharField(required=False, allow_blank=True, default="")
    sentiment = serializers.ChoiceField(
        choices=["all", "positive", "neutral", "negative"],
        required=False,
        default="all",
    )
    limit = serializers.IntegerField(min_value=1, max_value=100, default=20, required=False)


class NewsItemSerializer(serializers.Serializer):
    """Serializa una noticia del feed."""
    title = serializers.CharField()
    url = serializers.CharField()
    source = serializers.CharField()
    published_at = serializers.CharField()
    sentiment = serializers.CharField()
    relevance_score = serializers.FloatField(allow_null=True)
