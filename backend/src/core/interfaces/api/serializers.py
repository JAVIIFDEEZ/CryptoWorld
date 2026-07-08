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


class ResendVerificationRequestSerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/auth/verify-email/resend/."""
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


class UpdatePreferencesSerializer(serializers.Serializer):
    """
    Valida el cuerpo de PATCH /api/auth/me/.

    Todos los campos son opcionales: el cliente envía solo lo que cambia.
    Además de las preferencias, permite actualizar el nombre de usuario
    (la unicidad se comprueba en la vista, que conoce al usuario actual).
    """
    username = serializers.CharField(min_length=3, max_length=150, required=False)
    preferred_currency = serializers.ChoiceField(
        choices=["usd", "eur", "gbp"], required=False
    )
    notify_price_alerts = serializers.BooleanField(required=False)
    notify_market_digest = serializers.BooleanField(required=False)
    notify_risk_digest = serializers.BooleanField(required=False)

    def validate_username(self, value: str) -> str:
        return value.strip()

    def validate(self, data: dict) -> dict:
        if not data:
            raise serializers.ValidationError(
                "Debes enviar al menos un campo para actualizar."
            )
        return data


class ChangeEmailRequestSerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/auth/change-email/."""
    new_email = serializers.EmailField()
    password = serializers.CharField(write_only=True)


class ChangeEmailConfirmSerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/auth/change-email/confirm/."""
    token = serializers.CharField()


class Enable2FASerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/auth/2fa/enable/."""
    totp_code = serializers.CharField(min_length=6, max_length=6)


class Disable2FASerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/auth/2fa/disable/."""
    totp_code = serializers.CharField(min_length=6, max_length=6)


class Verify2FALoginSerializer(serializers.Serializer):
    """
    Valida el cuerpo de POST /api/auth/2fa/login/.

    Acepta totp_code (app autenticadora) o recovery_code (código de
    recuperación de un solo uso); exactamente uno de los dos.
    """
    pre_auth_token = serializers.CharField()
    totp_code = serializers.CharField(
        min_length=6, max_length=6, required=False, allow_blank=True, default=""
    )
    recovery_code = serializers.CharField(
        max_length=20, required=False, allow_blank=True, default=""
    )

    def validate(self, data: dict) -> dict:
        if bool(data.get("totp_code")) == bool(data.get("recovery_code")):
            raise serializers.ValidationError(
                "Debes enviar totp_code o recovery_code (solo uno de los dos)."
            )
        return data


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
    limit = serializers.IntegerField(min_value=10, max_value=1000, default=300, required=False)


class OhlcvCandleSerializer(serializers.Serializer):
    """Serializa una vela OHLCV."""
    open_time = serializers.CharField()
    open = serializers.CharField()
    high = serializers.CharField()
    low = serializers.CharField()
    close = serializers.CharField()
    volume = serializers.CharField()
    source = serializers.CharField()


class OnChainQuerySerializer(serializers.Serializer):
    """Valida query params de GET /api/blockchain/metrics/."""
    symbol = serializers.CharField(max_length=20, required=False, default="BTC")
    metric = serializers.ChoiceField(
        choices=[
            "active_addresses",
            "hashrate",
            "tx_count",
            "difficulty",
            "mempool_size",
            "miners_revenue",
            "transaction_fees",
            "avg_block_size",
        ],
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
    id = serializers.CharField(allow_blank=True)
    title = serializers.CharField()
    url = serializers.CharField()
    imageurl = serializers.CharField(allow_blank=True)
    source = serializers.CharField()
    published_at = serializers.CharField()
    sentiment = serializers.CharField()
    body = serializers.CharField(allow_blank=True)
    categories = serializers.CharField(allow_blank=True)
    relevance_score = serializers.FloatField(allow_null=True)

class DeleteAccountSerializer(serializers.Serializer):
    password = serializers.CharField(write_only=True)


# ── Analysis avanzado ──────────────────────────────────────────────

class CalculateAnalysisSerializer(serializers.Serializer):
    """Valida POST /api/analysis/calculate/."""
    asset_symbol = serializers.CharField(max_length=20)
    analysis_type = serializers.ChoiceField(
        choices=["RSI", "MACD", "SMA", "EMA", "BOLLINGER"],
    )
    interval = serializers.ChoiceField(
        choices=["1m", "5m", "15m", "1h", "4h", "1d"],
        default="1h",
        required=False,
    )
    limit = serializers.IntegerField(min_value=50, max_value=500, default=300, required=False)


class SignalsRequestSerializer(serializers.Serializer):
    """Valida POST /api/analysis/signals/."""
    asset_symbol = serializers.CharField(max_length=20)
    interval = serializers.ChoiceField(
        choices=["1m", "5m", "15m", "1h", "4h", "1d"],
        default="1h",
        required=False,
    )


class PredictionRequestSerializer(serializers.Serializer):
    """Valida POST /api/analysis/predict/."""
    asset_symbol = serializers.CharField(max_length=20)
    interval = serializers.ChoiceField(
        choices=["1m", "5m", "15m", "1h", "4h", "1d"],
        default="1h",
        required=False,
    )
    horizon = serializers.IntegerField(min_value=1, max_value=20, default=5, required=False)


class PatternsRequestSerializer(serializers.Serializer):
    """Valida POST /api/analysis/patterns/."""
    asset_symbol = serializers.CharField(max_length=20)
    interval = serializers.ChoiceField(
        choices=["1m", "5m", "15m", "1h", "4h", "1d"],
        default="1h",
        required=False,
    )


class BacktestRequestSerializer(serializers.Serializer):
    """Valida POST /api/analysis/backtest/."""
    asset_symbol = serializers.CharField(max_length=20)
    strategy = serializers.ChoiceField(
        choices=["rsi_reversal", "macd_crossover", "bollinger_bounce", "sma_crossover", "ema_trend"],
    )
    interval = serializers.ChoiceField(
        choices=["1m", "5m", "15m", "1h", "4h", "1d"],
        default="1h",
        required=False,
    )
    limit = serializers.IntegerField(min_value=60, max_value=1000, default=500, required=False)
    initial_capital = serializers.FloatField(min_value=100, max_value=1000000, default=10000, required=False)
    # Realismo de ejecución (opcional): costes y gestión de riesgo
    commission_bps = serializers.FloatField(min_value=0, max_value=100, default=0, required=False)
    slippage_bps = serializers.FloatField(min_value=0, max_value=100, default=0, required=False)
    stop_loss_pct = serializers.FloatField(min_value=0.005, max_value=0.5, required=False, allow_null=True)
    take_profit_pct = serializers.FloatField(min_value=0.005, max_value=1.0, required=False, allow_null=True)


# ── Portfolio ──────────────────────────────────────────────────────

class RobustBacktestRequestSerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/analysis/backtest/robust/."""
    asset_symbol = serializers.CharField(max_length=20)
    strategy = serializers.ChoiceField(
        choices=["rsi_reversal", "macd_crossover", "bollinger_bounce", "sma_crossover", "ema_trend"]
    )
    interval = serializers.ChoiceField(
        choices=["1h", "2h", "4h", "6h", "12h", "1d", "1w"],
        default="1d", required=False,
    )
    limit = serializers.IntegerField(min_value=250, max_value=1000, default=365, required=False)
    initial_capital = serializers.FloatField(
        min_value=100, max_value=1_000_000, default=10000.0, required=False
    )
    objective = serializers.ChoiceField(
        choices=["sharpe", "sortino", "calmar", "total_return"],
        default="sharpe", required=False,
    )
    preset = serializers.ChoiceField(
        choices=["fast", "balanced", "thorough"], default="balanced", required=False,
    )


class RobustCompareRequestSerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/analysis/backtest/robust/compare/."""
    asset_symbol = serializers.CharField(max_length=20)
    interval = serializers.ChoiceField(
        choices=["1h", "2h", "4h", "6h", "12h", "1d", "1w"],
        default="1d", required=False,
    )
    objective = serializers.ChoiceField(
        choices=["sharpe", "sortino", "calmar", "total_return"],
        default="sharpe", required=False,
    )
    preset = serializers.ChoiceField(
        choices=["fast", "balanced", "thorough"], default="fast", required=False,
    )


class StrategyGenerateRequestSerializer(serializers.Serializer):
    """Valida el cuerpo de POST /api/strategies/generate/."""
    asset_symbol = serializers.CharField(max_length=20)
    interval = serializers.ChoiceField(
        choices=["1h", "2h", "4h", "6h", "12h", "1d", "1w"],
        default="1d", required=False,
    )
    limit = serializers.IntegerField(min_value=300, max_value=2000, default=730, required=False)
    initial_capital = serializers.FloatField(
        min_value=100, max_value=1_000_000, default=10000.0, required=False
    )
    preset = serializers.ChoiceField(
        choices=["fast", "balanced", "thorough"], default="balanced", required=False,
    )
    optimizer = serializers.ChoiceField(
        choices=["single", "nsga"], default="single", required=False,
    )


class SpecRobustnessRequestSerializer(serializers.Serializer):
    """Valida POST /api/strategies/robustness/ — análisis profundo de un spec.

    Se puede pasar el spec directamente, o un strategy_id de una estrategia
    guardada (StrategyDefinition) de la que se recupera el spec."""
    spec = serializers.JSONField(required=False)
    strategy_id = serializers.IntegerField(required=False)
    asset_symbol = serializers.CharField(max_length=20)
    interval = serializers.ChoiceField(
        choices=["1h", "2h", "4h", "6h", "12h", "1d", "1w"],
        default="1d", required=False,
    )
    limit = serializers.IntegerField(min_value=250, max_value=2000, default=365, required=False)
    preset = serializers.ChoiceField(
        choices=["fast", "balanced", "thorough"], default="balanced", required=False,
    )

    def validate(self, attrs):
        if not attrs.get("spec") and not attrs.get("strategy_id"):
            raise serializers.ValidationError("Indica 'spec' o 'strategy_id'.")
        return attrs


class AddTradeSerializer(serializers.Serializer):
    """Valida POST /api/portfolio/trades/."""
    asset_symbol = serializers.CharField(max_length=20)
    trade_type = serializers.ChoiceField(choices=["BUY", "SELL"])
    quantity = serializers.FloatField(min_value=0.000000001)
    price_usd = serializers.FloatField(min_value=0.000000001)
    executed_at = serializers.DateTimeField()
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class TradeOutputSerializer(serializers.Serializer):
    """Serializa una operación del historial."""
    id = serializers.IntegerField()
    asset_symbol = serializers.CharField()
    asset_name = serializers.CharField()
    trade_type = serializers.CharField()
    quantity = serializers.CharField()
    price_usd = serializers.CharField()
    total_usd = serializers.CharField()
    notes = serializers.CharField()
    executed_at = serializers.CharField()
    created_at = serializers.CharField()


class PortfolioPositionSerializer(serializers.Serializer):
    """Serializa una posición abierta del portfolio."""
    asset_symbol = serializers.CharField()
    asset_name = serializers.CharField()
    logo_url = serializers.CharField(allow_null=True)
    quantity = serializers.CharField()
    avg_buy_price = serializers.CharField()
    total_invested = serializers.CharField()
    current_price = serializers.CharField()
    current_value = serializers.CharField()
    pnl_usd = serializers.CharField()
    pnl_pct = serializers.CharField()
    is_profit = serializers.BooleanField()
    position_type = serializers.CharField(default="LONG")


class TradeHistoryQuerySerializer(serializers.Serializer):
    """Valida query params de GET /api/portfolio/trades/."""
    symbol = serializers.CharField(required=False, allow_blank=True, default="")
    trade_type = serializers.ChoiceField(
        choices=["", "BUY", "SELL"],
        required=False,
        default="",
        allow_blank=True,
    )
    limit = serializers.IntegerField(min_value=1, max_value=500, default=50, required=False)


# ── Alerts ────────────────────────────────────────────────────────

class CreateAlertSerializer(serializers.Serializer):
    """Valida POST /api/alerts/."""
    asset_symbol = serializers.CharField(max_length=20)
    condition = serializers.ChoiceField(choices=["ABOVE", "BELOW"])
    threshold_price = serializers.FloatField(min_value=0.000000001)
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class AlertOutputSerializer(serializers.Serializer):
    """Serializa una alerta de precio."""
    id = serializers.IntegerField()
    asset_symbol = serializers.CharField()
    asset_name = serializers.CharField()
    condition = serializers.CharField()
    threshold_price = serializers.CharField()
    current_price = serializers.CharField()
    is_active = serializers.BooleanField()
    is_triggered = serializers.BooleanField()
    triggered_at = serializers.CharField(allow_null=True)
    notes = serializers.CharField()
    created_at = serializers.CharField()


# ── Positions (modelo explícito) ──────────────────────────────────

class OpenPositionSerializer(serializers.Serializer):
    """Valida POST /api/portfolio/positions/."""
    asset_symbol = serializers.CharField(max_length=20)
    direction = serializers.ChoiceField(choices=["LONG", "SHORT"])
    quantity = serializers.FloatField(min_value=0.000000001)
    entry_price = serializers.FloatField(min_value=0.000000001)
    opened_at = serializers.DateTimeField()
    label = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class ClosePositionSerializer(serializers.Serializer):
    """Valida POST /api/portfolio/positions/<id>/close/."""
    close_quantity = serializers.FloatField(min_value=0.000000001)
    close_price = serializers.FloatField(min_value=0.000000001)
    executed_at = serializers.DateTimeField()
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class AddToPositionSerializer(serializers.Serializer):
    """Valida POST /api/portfolio/positions/<id>/add/."""
    quantity = serializers.FloatField(min_value=0.000000001)
    entry_price = serializers.FloatField(min_value=0.000000001)
    executed_at = serializers.DateTimeField()
    notes = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class UpdatePositionSerializer(serializers.Serializer):
    """Valida PATCH /api/portfolio/positions/<id>/  (sólo etiqueta)."""
    label = serializers.CharField(max_length=200, allow_blank=True)


class PositionOutputSerializer(serializers.Serializer):
    """Serializa una posición del portfolio."""
    id = serializers.IntegerField()
    asset_symbol = serializers.CharField()
    asset_name = serializers.CharField()
    logo_url = serializers.CharField(allow_null=True)
    direction = serializers.CharField()
    status = serializers.CharField()
    label = serializers.CharField()
    avg_entry_price = serializers.CharField()
    open_quantity = serializers.CharField()
    initial_quantity = serializers.CharField()
    current_price = serializers.CharField()
    unrealized_pnl_usd = serializers.CharField()
    unrealized_pnl_pct = serializers.CharField()
    realized_pnl_usd = serializers.CharField()
    total_pnl_usd = serializers.CharField()
    is_profit = serializers.BooleanField()
    opened_at = serializers.CharField()
    closed_at = serializers.CharField(allow_null=True)
    trades_count = serializers.IntegerField()


class PositionSummaryOutputSerializer(serializers.Serializer):
    """Serializa el resumen de posiciones del usuario."""
    open_positions = PositionOutputSerializer(many=True)
    closed_positions = PositionOutputSerializer(many=True)
    total_unrealized_pnl_usd = serializers.CharField()
    total_realized_pnl_usd = serializers.CharField()
    open_long_count = serializers.IntegerField()
    open_short_count = serializers.IntegerField()


class PositionsQuerySerializer(serializers.Serializer):
    """Valida query params de GET /api/portfolio/positions/."""
    status = serializers.ChoiceField(
        choices=["", "OPEN", "CLOSED"],
        required=False,
        default="",
        allow_blank=True,
    )


# ── Watchlist ──────────────────────────────────────────────────────

class WatchlistItemSerializer(serializers.Serializer):
    """Serializa un activo de la watchlist del usuario."""
    symbol = serializers.CharField()
    name = serializers.CharField()
    logo_url = serializers.CharField(allow_null=True)
    current_price = serializers.CharField()
    price_change_24h = serializers.CharField()
    is_bullish_24h = serializers.BooleanField()
    added_at = serializers.CharField()


class WatchlistAddSerializer(serializers.Serializer):
    """Valida el body de POST /api/watchlist/ — añadir activo."""
    symbol = serializers.CharField(max_length=20)

