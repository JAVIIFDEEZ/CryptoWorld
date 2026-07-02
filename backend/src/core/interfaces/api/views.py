"""
interfaces/api/views.py â€” Controladores HTTP (DRF Views).

Esta es la Ãºnica capa que sabe de HTTP.
Responsabilidades:
  1. Recibir y validar la peticiÃ³n HTTP (usando serializers)
  2. Construir el DTO de entrada
  3. Invocar el caso de uso correspondiente (capa application)
  4. Serializar el DTO de salida â†’ respuesta HTTP

Lo que las views NUNCA deben hacer:
  - LÃ³gica de negocio
  - Consultas directas a la base de datos
  - Operaciones matemÃ¡ticas o financieras

Principio aplicado: Single Responsibility + Clean Architecture.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from django.core.cache import cache

from core.interfaces.api.serializers import (
    RegisterSerializer,
    LoginSerializer,
    LogoutSerializer,
    VerifyEmailSerializer,
    UpdatePreferencesSerializer,
    ChangeEmailRequestSerializer,
    ChangeEmailConfirmSerializer,
    PasswordResetRequestSerializer,
    ResendVerificationRequestSerializer,
    PasswordResetConfirmSerializer,
    ChangePasswordSerializer,
    Enable2FASerializer,
    Disable2FASerializer,
    Verify2FALoginSerializer,
    CryptoAssetSerializer,
    AnalysisRequestSerializer,
    AnalysisOutputSerializer,
    MarketOverviewSerializer,
    OhlcvQuerySerializer,
    OhlcvCandleSerializer,
    OnChainQuerySerializer,
    OnChainMetricPointSerializer,
    NewsQuerySerializer,
    NewsItemSerializer,
    DeleteAccountSerializer,
    RobustBacktestRequestSerializer,
    RobustCompareRequestSerializer,
    StrategyGenerateRequestSerializer,
    SpecRobustnessRequestSerializer,
    CalculateAnalysisSerializer,
    SignalsRequestSerializer,
    PredictionRequestSerializer,
    PatternsRequestSerializer,
    BacktestRequestSerializer,
    AddTradeSerializer,
    TradeOutputSerializer,
    PortfolioPositionSerializer,
    TradeHistoryQuerySerializer,
    CreateAlertSerializer,
    AlertOutputSerializer,
    OpenPositionSerializer,
    ClosePositionSerializer,
    AddToPositionSerializer,
    UpdatePositionSerializer,
    PositionOutputSerializer,
    PositionSummaryOutputSerializer,
    PositionsQuerySerializer,
    WatchlistItemSerializer,
    WatchlistAddSerializer,
)
from core.application.use_cases.register_user import RegisterUserUseCase
from core.application.use_cases.get_assets import GetAssetsUseCase
from core.application.use_cases.run_analysis import RunAnalysisUseCase
from core.application.use_cases.logout import LogoutUseCase
from core.application.use_cases.verify_email import VerifyEmailUseCase
from core.application.use_cases.send_verification_email import SendVerificationEmailUseCase
from core.application.use_cases.request_password_reset import RequestPasswordResetUseCase
from core.application.use_cases.confirm_password_reset import ConfirmPasswordResetUseCase
from core.tasks import dispatch_task
from core.tasks import send_verification_email as send_verification_email_task
from core.tasks import send_password_reset_email as send_password_reset_email_task
from core.application.use_cases.change_password import ChangePasswordUseCase
from core.application.use_cases.setup_2fa import Setup2FAUseCase
from core.application.use_cases.enable_2fa import Enable2FAUseCase
from core.application.use_cases.disable_2fa import Disable2FAUseCase
from core.application.use_cases.verify_2fa_login import Verify2FALoginUseCase, PreAuthToken
from core.application.use_cases.get_market_overview import GetMarketOverviewUseCase
from core.application.use_cases.get_asset_ohlcv import GetAssetOhlcvUseCase
from core.application.use_cases.get_onchain_metrics import GetOnChainMetricsUseCase
from core.application.use_cases.get_multichain_stats import GetMultiChainStatsUseCase
from core.application.use_cases.get_news_feed import GetNewsFeedUseCase
from core.application.use_cases.delete_user_account import DeleteUserAccountUseCase
from core.application.use_cases.get_signals_dashboard import GetSignalsDashboardUseCase
from core.application.use_cases.predict_price import PredictPriceUseCase
from core.application.use_cases.detect_patterns import DetectPatternsUseCase
from core.application.use_cases.run_backtest import RunBacktestUseCase
from core.application.use_cases.get_portfolio import GetPortfolioUseCase
from core.application.use_cases.add_trade import AddTradeUseCase
from core.application.use_cases.get_trade_history import GetTradeHistoryUseCase
from core.application.use_cases.delete_trade import DeleteTradeUseCase
from core.application.use_cases.open_position import OpenPositionUseCase
from core.application.use_cases.close_position import ClosePositionUseCase
from core.application.use_cases.scale_position import ScalePositionUseCase
from core.application.use_cases.get_positions import GetPositionsUseCase
from core.infrastructure.persistence.models import Position as PositionModel
from core.infrastructure.persistence.models import UserWatchlist as UserWatchlistModel
from core.infrastructure.persistence.models import CryptoAsset as CryptoAssetModel
from core.infrastructure.persistence.models import MarketDataSnapshot as MarketDataSnapshotModel
from core.application.use_cases.manage_alerts import (
    CreateAlertUseCase,
    ListAlertsUseCase,
    DeleteAlertUseCase,
    ToggleAlertUseCase,
)
from core.application.dto.auth_dto import (
    RegisterUserInputDTO,
    LoginInputDTO,
    LogoutInputDTO,
    VerifyEmailInputDTO,
    PasswordResetRequestDTO,
    PasswordResetConfirmDTO,
    ChangePasswordDTO,
    Enable2FADTO,
    Disable2FADTO,
    Verify2FALoginDTO,
)
from core.application.dto.asset_dto import (
    AnalysisRequestInputDTO,
    SignalsRequestDTO,
    PredictionRequestDTO,
    PatternsRequestDTO,
    BacktestRequestDTO,
)
from core.application.dto.portfolio_dto import (
    AddTradeInputDTO,
    OpenPositionInputDTO,
    ClosePositionInputDTO,
    AddToPositionInputDTO,
)
from core.application.dto.alerts_dto import CreateAlertInputDTO
from core.infrastructure.persistence.repositories_impl import (
    DjangoUserRepository,
    DjangoCryptoAssetRepository,
)
from core.infrastructure.persistence.models import User as UserModel
from core.domain.services.user_domain_service import UserDomainService


# â”€â”€ Health Check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class HealthCheckView(APIView):
    """
    GET /api/health — Comprobación de estado del servidor y sus dependencias.

    No requiere autenticación. Además del estado del proceso web, sondea
    las dependencias críticas (BD, cache Redis, broker Celery) para poder
    diagnosticar despliegues (Railway/Docker) de un vistazo. Devuelve
    siempre 200: el campo `status` distingue "ok" de "degraded" para no
    tumbar healthchecks de Docker por una dependencia secundaria.
    """
    permission_classes = [AllowAny]

    @staticmethod
    def _check_components() -> dict:
        from django.db import connection
        from django.conf import settings as dj_settings
        from kombu import Connection as BrokerConnection

        components = {}

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            components["database"] = "ok"
        except Exception:
            components["database"] = "error"

        try:
            cache.set("health_ping", "1", 5)
            components["cache"] = "ok" if cache.get("health_ping") == "1" else "error"
        except Exception:
            components["cache"] = "error"

        try:
            with BrokerConnection(dj_settings.CELERY_BROKER_URL, connect_timeout=2) as conn:
                conn.ensure_connection(max_retries=0)
            components["celery_broker"] = "ok"
        except Exception:
            components["celery_broker"] = "error"

        # Informativo: qué backend de email está activo (no afecta al estado)
        backend = dj_settings.EMAIL_BACKEND
        if "sendgrid" in backend:
            components["email_backend"] = "sendgrid"
        elif "smtp" in backend:
            components["email_backend"] = "smtp"
        else:
            components["email_backend"] = "console"

        return components

    def get(self, request):
        components = self._check_components()
        checks = {k: v for k, v in components.items() if k != "email_backend"}
        overall = "ok" if all(v == "ok" for v in checks.values()) else "degraded"
        return Response(
            {
                "status": overall,
                "version": "1.0.0",
                "service": "CryptoWorld API",
                "components": components,
            },
            status=status.HTTP_200_OK,
        )


# â”€â”€ Auth Views â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class RegisterView(APIView):
    """
    POST /api/auth/register â€” Registrar un nuevo usuario.

    Flujo:
      1. Validar datos de entrada con RegisterSerializer
      2. Construir DTO de entrada
      3. Delegar al caso de uso RegisterUserUseCase
      4. Enviar email de verificaciÃ³n
      5. Devolver respuesta 201 con datos del usuario creado
    """
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_register"

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated = serializer.validated_data

        user_repo = DjangoUserRepository()
        user_domain_service = UserDomainService(user_repo)
        use_case = RegisterUserUseCase(user_repo, user_domain_service)

        try:
            input_dto = RegisterUserInputDTO(
                email=validated["email"],
                username=validated["username"],
                password=validated["password"],
            )
            output_dto = use_case.execute(input_dto)

            # El repositorio crea el usuario sin contraseña;
            # la establecemos aquí usando el método del repositorio.
            user_repo.set_password(output_dto.id, validated["password"])

            # Enviar email de verificación de forma asíncrona (no bloquea la
            # respuesta HTTP); con fallback síncrono si no hay worker Celery.
            dispatch_task(send_verification_email_task, output_dto.id)

        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "id": output_dto.id,
                "email": output_dto.email,
                "username": output_dto.username,
                "message": "Cuenta creada. Revisa tu email para verificarla.",
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """
    POST /api/auth/login â€” Autenticar usuario y devolver tokens JWT.

    Si el usuario tiene 2FA activo, devuelve un token temporal (pre_auth_token)
    en lugar de los tokens completos. El cliente debe completar el segundo factor
    en POST /api/auth/2fa/login/.
    """
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_login"

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated = serializer.validated_data

        user = authenticate(
            request,
            username=validated["email"],
            password=validated["password"],
        )

        if user is None:
            return Response(
                {"error": "Credenciales inválidas."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        if not user.is_active:
            return Response(
                {"error": "Cuenta desactivada."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # PolÃ­tica de seguridad: no permitir login hasta verificar email
        if not user.is_email_verified:
            return Response(
                {
                    "error": "Debes verificar tu email antes de iniciar sesión.",
                    "error_code": "email_not_verified",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # Si 2FA estÃ¡ activo, emitir token temporal de pre-autenticaciÃ³n
        if user.is_2fa_enabled:
            pre_auth = PreAuthToken()
            pre_auth["user_id"] = user.pk
            return Response(
                {
                    "requires_2fa": True,
                    "pre_auth_token": str(pre_auth),
                },
                status=status.HTTP_200_OK,
            )

        # Sin 2FA: emitir tokens completos
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "access_token": str(refresh.access_token),
                "refresh_token": str(refresh),
                "user_id": user.pk,
                "email": user.email,
                "username": user.username,
                "is_admin": user.is_staff or user.is_superuser,
                "requires_2fa": False,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    """
    POST /api/auth/logout/ â€” Cerrar sesiÃ³n aÃ±adiendo el refresh_token a la blacklist.
    No requiere access token vÃ¡lido: el propio refresh_token es prueba suficiente.
    Esto permite hacer logout aunque el access token ya haya expirado.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            LogoutUseCase().execute(
                LogoutInputDTO(refresh_token=serializer.validated_data["refresh_token"])
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"message": "Sesión cerrada correctamente."}, status=status.HTTP_200_OK)


class MeView(APIView):
    """
    GET   /api/auth/me/ — Devolver los datos del usuario autenticado.
    PATCH /api/auth/me/ — Actualizar nombre de usuario y preferencias de
                          cuenta (moneda, notificaciones). El email tiene
                          su propio flujo seguro en /auth/change-email/.
    """
    permission_classes = [IsAuthenticated]

    @staticmethod
    def _serialize(user) -> dict:
        from core.application.use_cases.recovery_codes import remaining_recovery_codes

        return {
            "id": user.pk,
            "email": user.email,
            "pending_email": user.pending_email,
            "username": user.username,
            "is_active": user.is_active,
            "is_email_verified": user.is_email_verified,
            "is_2fa_enabled": user.is_2fa_enabled,
            "is_admin": user.is_staff or user.is_superuser,
            "date_joined": user.date_joined.isoformat(),
            "preferred_currency": user.preferred_currency,
            "notify_price_alerts": user.notify_price_alerts,
            "notify_market_digest": user.notify_market_digest,
            "recovery_codes_remaining": (
                remaining_recovery_codes(user) if user.is_2fa_enabled else 0
            ),
        }

    def get(self, request):
        return Response(self._serialize(request.user), status=status.HTTP_200_OK)

    def patch(self, request):
        serializer = UpdatePreferencesSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        validated = serializer.validated_data

        # Unicidad del username: se comprueba aquí porque el serializer
        # no conoce al usuario actual (hay que excluirlo de la búsqueda)
        new_username = validated.get("username")
        if new_username and (
            UserModel.objects.filter(username__iexact=new_username)
            .exclude(pk=user.pk)
            .exists()
        ):
            return Response(
                {"error": "El nombre de usuario ya está en uso."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated_fields = []
        for field, value in validated.items():
            setattr(user, field, value)
            updated_fields.append(field)
        user.save(update_fields=updated_fields)

        return Response(self._serialize(user), status=status.HTTP_200_OK)


class ChangeEmailRequestView(APIView):
    """
    POST /api/auth/change-email/ — Solicitar el cambio de email.

    Requiere la contraseña actual. Guarda la nueva dirección como
    pendiente y envía el enlace de confirmación AL NUEVO correo; el
    email de login no cambia hasta que se confirme.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_change_email"

    def post(self, request):
        from core.application.use_cases.change_email import RequestEmailChangeUseCase
        from core.tasks import send_email_change_email as send_email_change_task

        serializer = ChangeEmailRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        v = serializer.validated_data
        try:
            RequestEmailChangeUseCase().execute(
                user_id=request.user.pk,
                new_email=v["new_email"],
                password=v["password"],
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        dispatch_task(send_email_change_task, request.user.pk)

        return Response(
            {
                "message": (
                    "Te hemos enviado un enlace de confirmación a la nueva "
                    "dirección. Tu email actual sigue activo hasta que confirmes."
                ),
                "pending_email": request.user.pending_email,
            },
            status=status.HTTP_200_OK,
        )


class ChangeEmailConfirmView(APIView):
    """
    POST /api/auth/change-email/confirm/ — Confirmar el cambio con el
    token recibido en el nuevo correo. No requiere sesión: el usuario
    puede abrir el enlace desde cualquier dispositivo.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        from core.application.use_cases.change_email import ConfirmEmailChangeUseCase

        serializer = ChangeEmailConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            new_email = ConfirmEmailChangeUseCase().execute(
                serializer.validated_data["token"]
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"message": f"Email actualizado correctamente a {new_email}."},
            status=status.HTTP_200_OK,
        )


class VerifyEmailView(APIView):
    """
    GET /api/auth/verify-email/?uid=xxx&token=xxx
    Confirmar direcciÃ³n de email usando el link enviado por correo.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        serializer = VerifyEmailSerializer(data=request.query_params)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            VerifyEmailUseCase().execute(
                VerifyEmailInputDTO(
                    token=serializer.validated_data["token"],
                )
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"message": "Email verificado correctamente."},
            status=status.HTTP_200_OK,
        )


class ResendVerificationEmailView(APIView):
    """
    POST /api/auth/verify-email/resend/ â€” Reenviar email de verificaciÃ³n.
    No requiere autenticaciÃ³n para no bloquear el flujo cuando se exige
    email verificado antes de permitir login.
    """
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_resend_verification"

    def post(self, request):
        serializer = ResendVerificationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Respuesta indistinguible para evitar enumeraciÃ³n de emails.
        from core.infrastructure.persistence.models import User as UserModel
        user = UserModel.objects.filter(email=serializer.validated_data["email"]).first()
        if user and not user.is_email_verified:
            dispatch_task(send_verification_email_task, user.pk)

        return Response(
            {"message": "Si el email existe y no está verificado, recibirás un enlace."},
            status=status.HTTP_200_OK,
        )


class PasswordResetRequestView(APIView):
    """
    POST /api/auth/password-reset/ â€” Solicitar link de recuperaciÃ³n por email.
    No requiere autenticaciÃ³n. No revela si el email existe.
    """
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_password_reset"

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Enviar email de forma asíncrona (no revela si el email existe)
        dispatch_task(send_password_reset_email_task, serializer.validated_data["email"])

        # Respuesta siempre igual para no revelar si el email existe
        return Response(
            {"message": "Si el email existe, recibirás un enlace de recuperación."},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    """
    POST /api/auth/password-reset/confirm/ â€” Establecer nueva contraseÃ±a con el token del email.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        v = serializer.validated_data
        try:
            ConfirmPasswordResetUseCase().execute(
                PasswordResetConfirmDTO(
                    uid=v["uid"],
                    token=v["token"],
                    new_password=v["new_password"],
                )
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"message": "Contraseña restablecida correctamente."},
            status=status.HTTP_200_OK,
        )


class ChangePasswordView(APIView):
    """
    POST /api/auth/change-password/ â€” Cambiar contraseÃ±a estando autenticado.
    Requiere la contraseÃ±a actual como verificaciÃ³n adicional.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        v = serializer.validated_data
        try:
            ChangePasswordUseCase().execute(
                ChangePasswordDTO(
                    user_id=request.user.pk,
                    current_password=v["current_password"],
                    new_password=v["new_password"],
                )
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"message": "Contraseña cambiada correctamente."},
            status=status.HTTP_200_OK,
        )


# â”€â”€ 2FA Views â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class Setup2FAView(APIView):
    """
    POST /api/auth/2fa/setup/ â€” Iniciar configuraciÃ³n de 2FA.

    Devuelve el secreto TOTP y el QR en base64 para que el usuario
    escanee con Google Authenticator / Authy.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            output_dto = Setup2FAUseCase().execute(request.user.pk)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "totp_secret": output_dto.totp_secret,
                "qr_code_uri": output_dto.qr_code_uri,
                "qr_code_base64": output_dto.qr_code_base64,
                "message": (
                    "Escanea el QR con tu app autenticadora y luego "
                    "confirma con POST /api/auth/2fa/enable/."
                ),
            },
            status=status.HTTP_200_OK,
        )


class Enable2FAView(APIView):
    """
    POST /api/auth/2fa/enable/ â€” Activar 2FA confirmando el primer cÃ³digo TOTP.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = Enable2FASerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            recovery_codes = Enable2FAUseCase().execute(
                Enable2FADTO(
                    user_id=request.user.pk,
                    totp_code=serializer.validated_data["totp_code"],
                )
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "message": "2FA activado correctamente.",
                # Única vez que los códigos viajan en claro: el cliente debe
                # mostrarlos y pedir al usuario que los guarde.
                "recovery_codes": recovery_codes,
            },
            status=status.HTTP_200_OK,
        )


class Disable2FAView(APIView):
    """
    POST /api/auth/2fa/disable/ â€” Desactivar 2FA (requiere cÃ³digo TOTP vigente).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = Disable2FASerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            Disable2FAUseCase().execute(
                Disable2FADTO(
                    user_id=request.user.pk,
                    totp_code=serializer.validated_data["totp_code"],
                )
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"message": "2FA desactivado correctamente."},
            status=status.HTTP_200_OK,
        )


class Regenerate2FARecoveryCodesView(APIView):
    """
    POST /api/auth/2fa/recovery-codes/ — Regenerar códigos de recuperación.

    Requiere un código TOTP vigente (no basta la sesión: evita que un
    atacante con sesión secuestrada se lleve códigos nuevos). Invalida
    todos los códigos anteriores. Devuelve también cuántos quedaban.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        import pyotp
        from core.application.use_cases.recovery_codes import generate_recovery_codes

        serializer = Enable2FASerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = request.user
        if not user.is_2fa_enabled or not user.totp_secret:
            return Response(
                {"error": "2FA no está activado en esta cuenta."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(serializer.validated_data["totp_code"], valid_window=1):
            return Response(
                {"error": "Código TOTP incorrecto."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        codes = generate_recovery_codes(user)
        return Response(
            {
                "message": "Códigos de recuperación regenerados. Los anteriores ya no son válidos.",
                "recovery_codes": codes,
            },
            status=status.HTTP_200_OK,
        )


class Verify2FALoginView(APIView):
    """
    POST /api/auth/2fa/login/ â€” Segunda fase del login con 2FA.

    Recibe el pre_auth_token (obtenido del login normal) y el cÃ³digo TOTP.
    Si ambos son vÃ¡lidos, devuelve los tokens JWT completos.
    """
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_2fa"

    def post(self, request):
        serializer = Verify2FALoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        v = serializer.validated_data
        try:
            output_dto = Verify2FALoginUseCase().execute(
                Verify2FALoginDTO(
                    pre_auth_token=v["pre_auth_token"],
                    totp_code=v.get("totp_code", ""),
                    recovery_code=v.get("recovery_code", ""),
                )
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)

        return Response(
            {
                "access_token": output_dto.access_token,
                "refresh_token": output_dto.refresh_token,
                "user_id": output_dto.user_id,
                "email": output_dto.email,
                "username": output_dto.username,
                "is_admin": output_dto.is_admin,
            },
            status=status.HTTP_200_OK,
        )


# â”€â”€ Assets Views â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class AssetListView(APIView):
    """
    GET /api/assets â€” Listar todos los activos criptogrÃ¡ficos.
    Requiere autenticaciÃ³n JWT (Authorization: Bearer <token>).
    CachÃ© Redis 60 s: los activos los actualiza Celery; no necesitamos recargar la BD en cada request.
    """
    permission_classes = [IsAuthenticated]
    _CACHE_KEY = "asset_list"
    _CACHE_TTL = 60  # 60 segundos

    def get(self, request):
        cached = cache.get(self._CACHE_KEY)
        if cached is not None:
            return Response(cached, status=status.HTTP_200_OK)

        asset_repo = DjangoCryptoAssetRepository()
        use_case = GetAssetsUseCase(asset_repo)
        output_dtos = use_case.execute()

        if not output_dtos:
            mock_assets = _get_mock_assets()
            return Response(mock_assets, status=status.HTTP_200_OK)

        serializer = CryptoAssetSerializer(
            [vars(dto) for dto in output_dtos],
            many=True,
        )
        data = serializer.data
        cache.set(self._CACHE_KEY, data, self._CACHE_TTL)
        return Response(data, status=status.HTTP_200_OK)



class AssetSparklinesView(APIView):
    """
    GET /api/assets/sparklines/?symbols=BTC,ETH,SOL

    Devuelve el precio medio diario de los ultimos 7 dias por simbolo,
    construido desde MarketDataSnapshot (BD local, sin llamadas externas).

    Fuente primaria: MarketDataSnapshot — creado cada 10 min por Celery.
    Fuente de fallback: OHLCV de Binance/KuCoin, solo para activos con
    menos de 2 dias de historial local.

    Respuesta: { "BTC": [p1, p2, ...], "ETH": [...], ... }
    Maximo 10 simbolos por peticion.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from datetime import timedelta
        from django.utils import timezone
        from django.db.models import Avg
        from django.db.models.functions import TruncDate
        from collections import defaultdict

        raw = request.query_params.get("symbols", "")
        if not raw:
            return Response(
                {"error": "Parametro symbols requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        symbols = [s.strip().upper() for s in raw.split(",") if s.strip()][:10]

        # Clave de cache estable por conjunto de simbolos (orden normalizado),
        # con lectura read-through: si esta cacheado se devuelve sin tocar la BD.
        cache_key = "sparklines:" + ",".join(sorted(symbols))
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached, status=status.HTTP_200_OK)

        # ── 1. Precio medio diario desde MarketDataSnapshot (BD local) ────────
        # Cada asset synced por Celery acumula ~144 snapshots/dia (cada 10 min).
        # Agrupar por dia y promediar elimina ruido y da una curva limpia.
        cutoff = timezone.now() - timedelta(days=8)

        rows = (
            MarketDataSnapshotModel.objects
            .filter(asset__symbol__in=symbols, timestamp__gte=cutoff)
            .annotate(day=TruncDate("timestamp"))
            .values("asset__symbol", "day")
            .annotate(avg_price=Avg("price"))
            .order_by("asset__symbol", "day")
        )

        snap_map: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            snap_map[row["asset__symbol"]].append(float(row["avg_price"]))

        result: dict[str, list[float]] = {}
        needs_fallback: list[str] = []

        for symbol in symbols:
            prices = snap_map.get(symbol, [])
            if len(prices) >= 2:
                result[symbol] = prices
            else:
                needs_fallback.append(symbol)

        # ── 2. Fallback OHLCV para activos sin historial local suficiente ─────
        # Solo actua para assets muy nuevos (< 2 dias en el sistema).
        for symbol in needs_fallback:
            try:
                candles, _ = GetAssetOhlcvUseCase().execute(
                    symbol=symbol, interval="1d", limit=14
                )
                result[symbol] = [float(c.close) for c in candles]
            except Exception:
                result[symbol] = []

        cache.set(cache_key, result, 3600)  # 1 hora
        return Response(result, status=status.HTTP_200_OK)


# â”€â”€ Analysis Views â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class RunAnalysisView(APIView):
    """
    POST /api/analysis/run â€” Solicitar ejecuciÃ³n de anÃ¡lisis tÃ©cnico.
    Requiere autenticaciÃ³n JWT.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AnalysisRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated = serializer.validated_data
        use_case = RunAnalysisUseCase()

        input_dto = AnalysisRequestInputDTO(
            asset_symbol=validated["asset_symbol"],
            analysis_type=validated["analysis_type"],
        )
        output_dto = use_case.execute(input_dto)

        out_serializer = AnalysisOutputSerializer(vars(output_dto))
        return Response(out_serializer.data, status=status.HTTP_202_ACCEPTED)


# â”€â”€ Market Intelligence Views â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class MarketOverviewView(APIView):
    """
    GET /api/market/overview/ — Resumen global del mercado.
    Público: usado también desde la landing page (sin autenticación).
    Caché Redis 5 min: evita llamadas externas a CoinGecko/Alternative.me en cada request.
    """

    permission_classes = [AllowAny]
    _CACHE_KEY = "market_overview"
    _CACHE_TTL = 300  # 5 minutos

    def get(self, request):
        cached = cache.get(self._CACHE_KEY)
        if cached is not None:
            return Response(cached, status=status.HTTP_200_OK)

        output_dto = GetMarketOverviewUseCase().execute()
        serializer = MarketOverviewSerializer(vars(output_dto))
        data = serializer.data
        cache.set(self._CACHE_KEY, data, self._CACHE_TTL)
        return Response(data, status=status.HTTP_200_OK)

class ConfluenceCardView(APIView):
    """
    GET /api/assets/<symbol>/confluence/ — Ficha de confluencia técnica.

    Agrega tendencia, soportes/resistencias, Fibonacci, resumen de
    indicadores, veredicto con confianza y narrativa en español.
    Cacheada 1 h en el caso de uso (compartida con la landing SEO).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, symbol: str):
        from core.application.use_cases.get_confluence_card import (
            AssetNotFoundError,
            ConfluenceDataUnavailableError,
            GetConfluenceCardUseCase,
        )

        use_case = GetConfluenceCardUseCase(asset_repo=DjangoCryptoAssetRepository())
        try:
            dto = use_case.execute(symbol)
        except AssetNotFoundError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        except ConfluenceDataUnavailableError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        return Response(dto.as_dict(), status=status.HTTP_200_OK)


class FxRatesView(APIView):
    """
    GET /api/market/fx/ — Tasas de conversión USD→EUR/GBP.

    Público (datos no sensibles) y cacheado 1 hora: el frontend las usa
    para mostrar precios en la moneda preferida del usuario.
    """
    permission_classes = [AllowAny]
    _CACHE_KEY = "fx_rates"
    _CACHE_TTL = 3600  # 1 hora

    def get(self, request):
        from core.application.use_cases.get_fx_rates import GetFxRatesUseCase

        cached = cache.get(self._CACHE_KEY)
        if cached is not None:
            return Response(cached, status=status.HTTP_200_OK)

        data = GetFxRatesUseCase().execute()
        # El fallback no se cachea 1h completa: reintentar antes (5 min)
        ttl = self._CACHE_TTL if data["source"] == "coingecko" else 300
        cache.set(self._CACHE_KEY, data, ttl)
        return Response(data, status=status.HTTP_200_OK)


class AssetOhlcvView(APIView):

    """
    GET /api/assets/<symbol>/ohlcv/ — Serie de velas para gráficos interactivos.

    Cadena de fuentes: Binance → CoinGecko OHLC → error 404.
    La respuesta incluye source (binance o coingecko) para transparencia.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, symbol: str):
        from core.application.use_cases.get_asset_ohlcv import OhlcvNotAvailableError

        query_serializer = OhlcvQuerySerializer(data=request.query_params)
        if not query_serializer.is_valid():
            return Response(query_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        q = query_serializer.validated_data

        try:
            candles, source = GetAssetOhlcvUseCase().execute(
                symbol=symbol,
                interval=q["interval"],
                limit=q["limit"],
            )
        except OhlcvNotAvailableError as exc:
            return Response(
                {"error": str(exc), "source": None},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = OhlcvCandleSerializer([vars(c) for c in candles], many=True)
        return Response(
            {"source": source, "candles": serializer.data},
            status=status.HTTP_200_OK,
        )


class BlockchainMetricsView(APIView):
    """
    GET /api/blockchain/metrics/ â€” MÃ©tricas on-chain filtrables.
    Requiere autenticaciÃ³n JWT.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        query_serializer = OnChainQuerySerializer(data=request.query_params)
        if not query_serializer.is_valid():
            return Response(query_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        q = query_serializer.validated_data
        result = GetOnChainMetricsUseCase().execute(
            symbol=q["symbol"],
            metric=q["metric"],
            days=q["days"],
        )
        if result.get("error"):
            return Response(result, status=status.HTTP_200_OK)
        # Devolver timestamp como int (Unix segundos) y value como float para el frontend
        data_points = [
            {"timestamp": int(p.timestamp), "value": float(p.value)}
            for p in result["points"]
        ]
        return Response({
            "symbol": result.get("symbol"),
            "metric": result.get("metric"),
            "metric_label": result.get("metric_label"),
            "description": result.get("description"),
            "timespan": result.get("timespan"),
            "total_points": result.get("total_points"),
            "source": result.get("source"),
            "data": data_points,
        }, status=status.HTTP_200_OK)




class MultiChainStatsView(APIView):
    """
    GET /api/blockchain/multichain/ - Estadisticas on-chain actuales (snapshot).
    Soporta: BTC, ETH, LTC, DOGE, BCH, XRP, ADA, DOT, XLM, XMR via Blockchair.
    Requiere autenticacion JWT.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        symbol = request.query_params.get("symbol", "ETH").upper()
        result = GetMultiChainStatsUseCase().execute(symbol=symbol)
        return Response(result, status=status.HTTP_200_OK)


class WalletChainsView(APIView):
    """
    GET /api/blockchain/wallet/chains/ — Redes soportadas por el explorador de
    wallets on-chain (Blockscout).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.application.use_cases.get_wallet_overview import GetSupportedChainsUseCase

        return Response(GetSupportedChainsUseCase().execute(), status=status.HTTP_200_OK)


class WalletOverviewView(APIView):
    """
    GET /api/blockchain/wallet/?chain=ethereum&address=0x... — Retrato on-chain de
    una dirección: saldo nativo y su valor en USD, cartera de tokens ERC-20
    valorada, valor total y transacciones recientes (vía Blockscout, datos reales).
    """
    permission_classes = [IsAuthenticated]
    _CACHE_TTL = 120  # segundos — los saldos cambian poco entre bloques

    def get(self, request):
        from core.application.use_cases.get_wallet_overview import GetWalletOverviewUseCase

        chain = (request.query_params.get("chain") or "ethereum").strip().lower()
        address = (request.query_params.get("address") or "").strip()

        cache_key = f"wallet_overview:{chain}:{address.lower()}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached, status=status.HTTP_200_OK)

        result = GetWalletOverviewUseCase().execute(chain=chain, address=address)
        if result.get("error"):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        cache.set(cache_key, result, self._CACHE_TTL)
        return Response(result, status=status.HTTP_200_OK)


class WalletBalanceHistoryView(APIView):
    """
    GET /api/blockchain/wallet/history/?chain=ethereum&address=0x... — Serie diaria
    del saldo nativo de una dirección (curva de patrimonio on-chain) vía Blockscout.
    """
    permission_classes = [IsAuthenticated]
    _CACHE_TTL = 600  # segundos — la serie diaria cambia poco

    def get(self, request):
        from core.application.use_cases.get_wallet_overview import GetWalletBalanceHistoryUseCase

        chain = (request.query_params.get("chain") or "ethereum").strip().lower()
        address = (request.query_params.get("address") or "").strip()
        cache_key = f"wallet_history:{chain}:{address.lower()}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached, status=status.HTTP_200_OK)

        result = GetWalletBalanceHistoryUseCase().execute(chain=chain, address=address)
        if result.get("error"):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        cache.set(cache_key, result, self._CACHE_TTL)
        return Response(result, status=status.HTTP_200_OK)


class ChainHealthView(APIView):
    """
    GET /api/blockchain/health/?chain=ethereum — Salud de red y rastreador de gas:
    precios de gas (Gwei), utilización, tiempo de bloque y precio del nativo, con
    aviso de gas barato/normal/caro específico por red (vía Blockscout).
    """
    permission_classes = [IsAuthenticated]
    _CACHE_TTL = 60  # segundos — el gas cambia bloque a bloque

    def get(self, request):
        from core.application.use_cases.get_chain_health import GetChainHealthUseCase

        chain = (request.query_params.get("chain") or "ethereum").strip().lower()
        cache_key = f"chain_health:{chain}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached, status=status.HTTP_200_OK)

        result = GetChainHealthUseCase().execute(chain=chain)
        if result.get("error"):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        cache.set(cache_key, result, self._CACHE_TTL)
        return Response(result, status=status.HTTP_200_OK)


class WhaleMovementsView(APIView):
    """
    GET /api/blockchain/movements/?chain=ethereum&min_usd=100000&limit=25 — Mayores
    movimientos on-chain recientes (transferencias nativas + de tokens ERC-20)
    ordenados por valor en USD, con etiquetas de entidad cuando se conocen.
    """
    permission_classes = [IsAuthenticated]
    _CACHE_TTL = 60  # segundos

    def get(self, request):
        from core.application.use_cases.get_whale_movements import GetWhaleMovementsUseCase

        chain = (request.query_params.get("chain") or "ethereum").strip().lower()
        try:
            min_usd = float(request.query_params.get("min_usd", 100000))
        except (TypeError, ValueError):
            min_usd = 100000.0
        try:
            limit = min(int(request.query_params.get("limit", 25)), 100)
        except (TypeError, ValueError):
            limit = 25

        cache_key = f"whale_movements:{chain}:{int(min_usd)}:{limit}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached, status=status.HTTP_200_OK)

        result = GetWhaleMovementsUseCase().execute(chain=chain, min_usd=min_usd, limit=limit)
        if result.get("error"):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        cache.set(cache_key, result, self._CACHE_TTL)
        return Response(result, status=status.HTTP_200_OK)


class OnChainPressureView(APIView):
    """
    GET /api/blockchain/pressure/?chain=ethereum&hours=24 — Indicador de presión
    on-chain: flujo de depósitos (presión vendedora potencial) vs retiradas
    (acumulación) de exchanges sobre el histórico propio de grandes movimientos,
    con puntuación en [-1, +1], serie temporal y mayores movimientos.
    """
    permission_classes = [IsAuthenticated]
    _CACHE_TTL = 120  # segundos

    def get(self, request):
        from core.application.use_cases.onchain_pressure import OnChainPressureUseCase

        chain = (request.query_params.get("chain") or "ethereum").strip().lower()
        try:
            hours = min(max(int(request.query_params.get("hours", 24)), 1), 720)
        except (TypeError, ValueError):
            hours = 24

        cache_key = f"onchain_pressure:{chain}:{hours}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached, status=status.HTTP_200_OK)

        result = OnChainPressureUseCase().execute(chain=chain, hours=hours)
        cache.set(cache_key, result, self._CACHE_TTL)
        return Response(result, status=status.HTTP_200_OK)


class SmartMoneyView(APIView):
    """
    GET /api/blockchain/smartmoney/?chain=ethereum&days=30 — Radar de dinero
    inteligente: direcciones cuyos depósitos/retiradas de exchanges anticiparon
    el precio (acierto y retorno capturado ponderados por tamaño).
    """
    permission_classes = [IsAuthenticated]
    _CACHE_TTL = 600  # segundos — evalúa precios por cada activo implicado

    def get(self, request):
        from core.application.use_cases.get_smart_money import GetSmartMoneyUseCase

        chain = (request.query_params.get("chain") or "ethereum").strip().lower()
        try:
            days = min(max(int(request.query_params.get("days", 30)), 1), 90)
        except (TypeError, ValueError):
            days = 30

        cache_key = f"smart_money:{chain}:{days}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached, status=status.HTTP_200_OK)

        result = GetSmartMoneyUseCase().execute(chain=chain, days=days)
        cache.set(cache_key, result, self._CACHE_TTL)
        return Response(result, status=status.HTTP_200_OK)


class AddressWatchlistView(APIView):
    """
    GET  /api/blockchain/watchlist/ — Direcciones on-chain vigiladas del usuario,
         con su saldo y las alertas recientes de movimientos.
    POST /api/blockchain/watchlist/ — Añade una dirección.
         Body: {"chain": "ethereum", "address": "0x...", "label"?: str, "threshold_pct"?: float}.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.application.use_cases.watchlist import WatchlistUseCase

        return Response(WatchlistUseCase().execute(owner=request.user), status=status.HTTP_200_OK)

    def post(self, request):
        from core.application.use_cases.watchlist import AddWatchedAddressUseCase

        result = AddWatchedAddressUseCase().execute(
            owner=request.user,
            chain=request.data.get("chain", "ethereum"),
            address=request.data.get("address", ""),
            label=request.data.get("label", ""),
            threshold_pct=request.data.get("threshold_pct", 5.0),
        )
        if result.get("error"):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_201_CREATED)


class AddressWatchlistItemView(APIView):
    """DELETE /api/blockchain/watchlist/<id>/ — Elimina una dirección vigilada."""
    permission_classes = [IsAuthenticated]

    def delete(self, request, watch_id: int):
        from core.application.use_cases.watchlist import RemoveWatchedAddressUseCase

        result = RemoveWatchedAddressUseCase().execute(owner=request.user, watch_id=watch_id)
        if result.get("error"):
            return Response(result, status=status.HTTP_404_NOT_FOUND)
        return Response(result, status=status.HTTP_200_OK)


class NotificationsView(APIView):
    """
    GET  /api/notifications/ — Feed unificado de notificaciones del usuario
         (señales, ballenas, predicciones resueltas, alertas de precio) + nº de
         no leídas.
    POST /api/notifications/seen/ — Marca todas como leídas.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.application.use_cases.notifications import NotificationsFeedUseCase

        try:
            limit = min(int(request.query_params.get("limit", 30)), 100)
        except (TypeError, ValueError):
            limit = 30
        return Response(
            NotificationsFeedUseCase().execute(owner=request.user, limit=limit),
            status=status.HTTP_200_OK,
        )


class NotificationsSeenView(APIView):
    """POST /api/notifications/seen/ — Marca todas las notificaciones como leídas."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from core.application.use_cases.notifications import MarkNotificationsSeenUseCase

        return Response(
            MarkNotificationsSeenUseCase().execute(owner=request.user),
            status=status.HTTP_200_OK,
        )


class NewsFeedView(APIView):
    """
    GET /api/news/ â€” Feed de noticias con filtro de sentimiento.
    Requiere autenticaciÃ³n JWT.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        query_serializer = NewsQuerySerializer(data=request.query_params)
        if not query_serializer.is_valid():
            return Response(query_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        q = query_serializer.validated_data
        result = GetNewsFeedUseCase().execute(
            query=q["q"],
            sentiment=q["sentiment"],
            limit=q["limit"],
        )
        if result.get("error"):
            return Response(result, status=status.HTTP_200_OK)
        serializer = NewsItemSerializer([vars(i) for i in result["items"]], many=True)
        return Response({
            "total": result.get("total", len(result["items"])),
            "source": result.get("source", "cryptocompare"),
            "data": serializer.data,
        }, status=status.HTTP_200_OK)


# â”€â”€ Mock data â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def _get_mock_assets() -> list:
    """Datos de ejemplo para desarrollo cuando la BD estÃ¡ vacÃ­a."""
    return [
        {
            "id": 1, "symbol": "BTC", "name": "Bitcoin",
            "current_price": "65000.00", "market_cap": "1280000000000",
            "volume_24h": "35000000000", "price_change_24h": "2.45",
            "is_bullish_24h": True,
        },
        {
            "id": 2, "symbol": "ETH", "name": "Ethereum",
            "current_price": "3200.00", "market_cap": "385000000000",
            "volume_24h": "18000000000", "price_change_24h": "-1.20",
            "is_bullish_24h": False,
        },
        {
            "id": 3, "symbol": "SOL", "name": "Solana",
            "current_price": "142.00", "market_cap": "62000000000",
            "volume_24h": "3200000000", "price_change_24h": "5.10",
            "is_bullish_24h": True,
        },
    ]


class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        serializer = DeleteAccountSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(
            request,
            username=request.user.email,
            password=serializer.validated_data['password'],
        )
        if user is None:
            return Response({'error': 'Contraseña incorrecta.'}, status=status.HTTP_400_BAD_REQUEST)

        repo = DjangoUserRepository()
        use_case = DeleteUserAccountUseCase(repo)
        result = use_case.execute(request.user.id)

        if result.get('success'):
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response({'error': result.get('error')}, status=status.HTTP_400_BAD_REQUEST)


# ── Analysis avanzado Views ────────────────────────────────────────


class CalculateAnalysisView(APIView):
    """
    POST /api/analysis/calculate/ — Calcula un indicador técnico con datos reales.
    Reemplaza al antiguo RunAnalysisView con cálculos reales.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = CalculateAnalysisSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        v = serializer.validated_data
        use_case = RunAnalysisUseCase()
        input_dto = AnalysisRequestInputDTO(
            asset_symbol=v["asset_symbol"],
            analysis_type=v["analysis_type"],
            interval=v.get("interval", "1h"),
            limit=v.get("limit", 300),
        )
        output = use_case.execute(input_dto)
        return Response(vars(output), status=status.HTTP_200_OK)


class SignalsDashboardView(APIView):
    """
    POST /api/analysis/signals/ — Panel multi-indicador con semáforos.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SignalsRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        v = serializer.validated_data
        result = GetSignalsDashboardUseCase().execute(
            SignalsRequestDTO(
                asset_symbol=v["asset_symbol"],
                interval=v.get("interval", "1h"),
            )
        )
        return Response(result, status=status.HTTP_200_OK)


class MtfConfluenceView(APIView):
    """
    GET /api/analysis/mtf/?asset_symbol=BTC — Confluencia multi-marco temporal:
    señales multi-indicador en 15m/1h/4h/1d con puntuación de alineación
    ponderada (los marcos altos pesan más) y % de acuerdo entre marcos.
    """
    permission_classes = [IsAuthenticated]
    _CACHE_TTL = 300  # segundos — calcula 4 marcos, se cachea 5 min

    def get(self, request):
        from core.application.use_cases.get_mtf_confluence import GetMtfConfluenceUseCase

        symbol = (request.query_params.get("asset_symbol") or "").upper().strip()
        if not symbol:
            return Response({"error": "Falta asset_symbol."}, status=status.HTTP_400_BAD_REQUEST)

        cache_key = f"mtf_confluence:{symbol}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached, status=status.HTTP_200_OK)

        result = GetMtfConfluenceUseCase().execute(asset_symbol=symbol)
        if result.get("error"):
            return Response(result, status=status.HTTP_200_OK)
        cache.set(cache_key, result, self._CACHE_TTL)
        return Response(result, status=status.HTTP_200_OK)


class PriceStructureView(APIView):
    """
    GET /api/analysis/levels/?asset_symbol=BTC&interval=1h — Estructura de
    precio: niveles de soporte/resistencia por agrupación de pivotes (fuerza =
    nº de toques) y divergencias RSI/precio recientes.
    """
    permission_classes = [IsAuthenticated]
    _CACHE_TTL = 300  # segundos

    def get(self, request):
        from core.application.use_cases.get_price_structure import GetPriceStructureUseCase

        symbol = (request.query_params.get("asset_symbol") or "").upper().strip()
        interval = (request.query_params.get("interval") or "1h").strip()
        if not symbol:
            return Response({"error": "Falta asset_symbol."}, status=status.HTTP_400_BAD_REQUEST)

        cache_key = f"price_structure:{symbol}:{interval}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached, status=status.HTTP_200_OK)

        result = GetPriceStructureUseCase().execute(asset_symbol=symbol, interval=interval)
        if result.get("error"):
            return Response(result, status=status.HTTP_200_OK)
        cache.set(cache_key, result, self._CACHE_TTL)
        return Response(result, status=status.HTTP_200_OK)


class PredictPriceView(APIView):
    """
    POST /api/analysis/predict/ — Predicción ML de dirección de precio.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PredictionRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        v = serializer.validated_data
        result = PredictPriceUseCase().execute(
            PredictionRequestDTO(
                asset_symbol=v["asset_symbol"],
                interval=v.get("interval", "1h"),
                horizon=v.get("horizon", 5),
            ),
            owner=request.user,
        )
        return Response(result, status=status.HTTP_200_OK)


class PredictionTrackRecordView(APIView):
    """
    GET /api/analysis/predictions/ — Rendimiento realizado (en vivo) de las
    predicciones del usuario: precisión global, segmentada por veredicto del
    modelo y registros recientes con su estado (acierto/fallo/pendiente).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.application.use_cases.track_predictions import PredictionTrackRecordUseCase

        try:
            limit = min(int(request.query_params.get("limit", 30)), 100)
        except (TypeError, ValueError):
            limit = 30
        return Response(
            PredictionTrackRecordUseCase().execute(owner=request.user, limit=limit),
            status=status.HTTP_200_OK,
        )


class PredictionMonitoringView(APIView):
    """
    GET /api/analysis/predictions/monitoring/ — Monitorización de *drift* del
    modelo: precisión prometida (OOS) vs realizada en vivo, serie temporal de
    precisión y estado de alerta (ok/watch/drift) para disparar reoptimización.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.application.use_cases.track_predictions import PredictionMonitoringUseCase

        try:
            buckets = min(max(int(request.query_params.get("buckets", 8)), 2), 24)
        except (TypeError, ValueError):
            buckets = 8
        return Response(
            PredictionMonitoringUseCase().execute(owner=request.user, buckets=buckets),
            status=status.HTTP_200_OK,
        )


class DetectPatternsView(APIView):
    """
    POST /api/analysis/patterns/ — Detección de patrones de velas.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PatternsRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        v = serializer.validated_data
        result = DetectPatternsUseCase().execute(
            PatternsRequestDTO(
                asset_symbol=v["asset_symbol"],
                interval=v.get("interval", "1h"),
            )
        )
        return Response(result, status=status.HTTP_200_OK)


class RunBacktestView(APIView):
    """
    POST /api/analysis/backtest/ — Backtesting de estrategias.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = BacktestRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        v = serializer.validated_data
        result = RunBacktestUseCase().execute(
            BacktestRequestDTO(
                asset_symbol=v["asset_symbol"],
                strategy=v["strategy"],
                interval=v.get("interval", "1h"),
                limit=v.get("limit", 500),
                initial_capital=v.get("initial_capital", 10000.0),
                commission_bps=v.get("commission_bps", 0.0),
                slippage_bps=v.get("slippage_bps", 0.0),
                stop_loss_pct=v.get("stop_loss_pct"),
                take_profit_pct=v.get("take_profit_pct"),
            )
        )
        return Response(result, status=status.HTTP_200_OK)


class RobustBacktestLaunchView(APIView):
    """
    POST /api/analysis/backtest/robust/ — Lanza la suite de robustez como
    tarea Celery (cientos de backtests) y devuelve un job_id sin bloquear.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "robust_backtest"

    def post(self, request):
        serializer = RobustBacktestRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        from core.tasks import run_robust_backtest as task

        v = serializer.validated_data
        async_result = task.delay(
            asset_symbol=v["asset_symbol"],
            strategy=v["strategy"],
            interval=v.get("interval", "1d"),
            limit=v.get("limit", 365),
            initial_capital=v.get("initial_capital", 10000.0),
            objective=v.get("objective", "sharpe"),
            preset=v.get("preset", "balanced"),
        )
        return Response(
            {
                "job_id": async_result.id,
                "status": async_result.state,
                "poll_url": f"/api/analysis/backtest/robust/{async_result.id}/",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class RobustBacktestCompareView(APIView):
    """
    POST /api/analysis/backtest/robust/compare/ — Lanza la comparación de las
    5 estrategias como tarea Celery y devuelve un job_id. El resultado se
    consulta con el mismo endpoint de estado (.../robust/<job_id>/).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RobustCompareRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        from core.tasks import compare_strategies_robustness as task

        v = serializer.validated_data
        async_result = task.delay(
            asset_symbol=v["asset_symbol"],
            interval=v.get("interval", "1d"),
            objective=v.get("objective", "sharpe"),
            preset=v.get("preset", "fast"),
        )
        return Response(
            {
                "job_id": async_result.id,
                "status": async_result.state,
                "poll_url": f"/api/analysis/backtest/robust/{async_result.id}/",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class RobustBacktestStatusView(APIView):
    """
    GET /api/analysis/backtest/robust/<job_id>/ — Estado/resultado del job.

    status: PENDING | STARTED | SUCCESS | FAILURE. Con SUCCESS incluye el
    informe completo en `result`.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id: str):
        from celery.result import AsyncResult
        from config.celery import app

        res = AsyncResult(job_id, app=app)
        payload = {"job_id": job_id, "status": res.state}

        if res.successful():
            payload["result"] = res.result
        elif res.failed():
            payload["error"] = "La suite de robustez falló durante la ejecución."

        return Response(payload, status=status.HTTP_200_OK)


class StrategyGenerateLaunchView(APIView):
    """
    POST /api/strategies/generate/ — Lanza el generador genético de estrategias
    como tarea Celery (evolución + gating de robustez, cientos de backtests) y
    devuelve un job_id sin bloquear.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "strategy_generate"

    def post(self, request):
        serializer = StrategyGenerateRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        from core.tasks import generate_strategies as task

        v = serializer.validated_data
        async_result = task.delay(
            asset_symbol=v["asset_symbol"],
            interval=v.get("interval", "1d"),
            limit=v.get("limit", 730),
            initial_capital=v.get("initial_capital", 10000.0),
            preset=v.get("preset", "balanced"),
            optimizer=v.get("optimizer", "single"),
        )
        return Response(
            {
                "job_id": async_result.id,
                "status": async_result.state,
                "poll_url": f"/api/strategies/generate/{async_result.id}/",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class StrategyGenerateStatusView(APIView):
    """
    GET /api/strategies/generate/<job_id>/ — Estado/resultado del generador.

    status: PENDING | STARTED | SUCCESS | FAILURE. Con SUCCESS incluye el
    informe completo con el ranking de finalistas en `result`.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id: str):
        from celery.result import AsyncResult
        from config.celery import app

        res = AsyncResult(job_id, app=app)
        payload = {"job_id": job_id, "status": res.state}

        if res.successful():
            payload["result"] = res.result
        elif res.failed():
            payload["error"] = "El generador de estrategias falló durante la ejecución."

        return Response(payload, status=status.HTTP_200_OK)


class SpecRobustnessLaunchView(APIView):
    """
    POST /api/strategies/robustness/ — Análisis profundo de robustez de una
    estrategia generada (su StrategySpec). Suite completa + validación cruzada
    multi-activo, como tarea Celery; devuelve un job_id.

    Cuerpo: spec (objeto) o strategy_id (de una guardada) + asset_symbol.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "strategy_robustness"

    def post(self, request):
        serializer = SpecRobustnessRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        v = serializer.validated_data
        spec = v.get("spec")
        if spec is None:
            from core.infrastructure.persistence.models import StrategyDefinition
            obj = StrategyDefinition.objects.filter(id=v["strategy_id"]).first()
            if obj is None:
                return Response({"error": "Estrategia no encontrada."}, status=status.HTTP_404_NOT_FOUND)
            spec = obj.spec

        from core.domain.services.strategy_spec import validate_spec
        if not validate_spec(spec):
            return Response({"error": "El spec no es una estrategia válida."}, status=status.HTTP_400_BAD_REQUEST)

        from core.tasks import analyze_spec_robustness as task

        async_result = task.delay(
            spec=spec,
            asset_symbol=v["asset_symbol"],
            interval=v.get("interval", "1d"),
            limit=v.get("limit", 365),
            preset=v.get("preset", "balanced"),
        )
        return Response(
            {
                "job_id": async_result.id,
                "status": async_result.state,
                "poll_url": f"/api/strategies/robustness/{async_result.id}/",
            },
            status=status.HTTP_202_ACCEPTED,
        )


class SpecRobustnessStatusView(APIView):
    """GET /api/strategies/robustness/<job_id>/ — Estado/resultado del análisis."""
    permission_classes = [IsAuthenticated]

    def get(self, request, job_id: str):
        from celery.result import AsyncResult
        from config.celery import app

        res = AsyncResult(job_id, app=app)
        payload = {"job_id": job_id, "status": res.state}
        if res.successful():
            payload["result"] = res.result
        elif res.failed():
            payload["error"] = "El análisis de robustez falló durante la ejecución."
        return Response(payload, status=status.HTTP_200_OK)


class SavedStrategiesListView(APIView):
    """
    GET /api/strategies/ — Historial de estrategias generadas que pasaron el
    gating de robustez (StrategyDefinition), las más recientes primero.

    Filtros opcionales: ?asset_symbol=BTC, ?interval=1d, ?limit=50.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.infrastructure.persistence.models import StrategyDefinition

        qs = StrategyDefinition.objects.select_related("asset").filter(passed_gating=True)
        symbol = request.query_params.get("asset_symbol")
        interval = request.query_params.get("interval")
        if symbol:
            qs = qs.filter(asset__symbol=symbol.upper())
        if interval:
            qs = qs.filter(interval=interval)

        try:
            limit = min(int(request.query_params.get("limit", 50)), 200)
        except (TypeError, ValueError):
            limit = 50

        qs = qs.order_by("-created_at")[:limit]
        items = [
            {
                "id": s.id,
                "asset_symbol": s.asset.symbol if s.asset else None,
                "name": s.name,
                "spec": s.spec,
                "spec_hash": s.spec_hash,
                "interval": s.interval,
                "rank": s.rank,
                "fitness": s.fitness,
                "robustness_metrics": s.robustness_metrics,
                "gating_checks": s.gating_checks,
                "holdout_metrics": s.holdout_metrics,
                "status": s.status,
                "is_monitored": s.is_monitored,
                "last_signal": s.last_signal,
                "last_signal_at": s.last_signal_at.isoformat() if s.last_signal_at else None,
                "generated_at": s.generated_at.isoformat() if s.generated_at else None,
                "created_at": s.created_at.isoformat(),
            }
            for s in qs
        ]
        return Response({"count": len(items), "results": items}, status=status.HTTP_200_OK)


class StrategyMonitorView(APIView):
    """
    POST /api/strategies/<id>/monitor/ — Activa o desactiva la monitorización en
    vivo de una estrategia generada. Body: {"active": true|false}. Al activar,
    el usuario pasa a ser su dueño y recibirá notificaciones de cambio de señal.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, strategy_id: int):
        from core.infrastructure.persistence.models import StrategyDefinition

        obj = StrategyDefinition.objects.filter(id=strategy_id).first()
        if obj is None:
            return Response({"error": "Estrategia no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        active = bool(request.data.get("active", True))
        obj.is_monitored = active
        obj.owner = request.user if active else None
        obj.save(update_fields=["is_monitored", "owner", "updated_at"])
        return Response({"strategy_id": obj.id, "is_monitored": obj.is_monitored}, status=status.HTTP_200_OK)


class StrategySignalView(APIView):
    """
    GET /api/strategies/<id>/signal/ — Señal actual (BUY/SELL/HOLD) de la
    estrategia sobre los datos más recientes, con el estado de cada condición.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, strategy_id: int):
        from core.application.use_cases.monitor_strategies import StrategySignalUseCase

        result = StrategySignalUseCase().execute(strategy_id)
        code = status.HTTP_404_NOT_FOUND if result.get("error") == "Estrategia no encontrada." else status.HTTP_200_OK
        return Response(result, status=code)


class RecentSignalEventsView(APIView):
    """
    GET /api/strategies/signals/recent/ — Historial reciente de señales disparadas
    por las estrategias monitorizadas del usuario (las más recientes primero).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.infrastructure.persistence.models import StrategySignalEvent

        try:
            limit = min(int(request.query_params.get("limit", 30)), 100)
        except (TypeError, ValueError):
            limit = 30

        qs = (
            StrategySignalEvent.objects
            .select_related("strategy", "strategy__asset")
            .filter(owner=request.user)
            .order_by("-created_at")[:limit]
        )
        events = [
            {
                "id": e.id,
                "strategy_id": e.strategy_id,
                "asset_symbol": e.strategy.asset.symbol if e.strategy.asset else None,
                "name": e.strategy.name,
                "signal": e.signal,
                "price": e.price,
                "notified": e.notified,
                "created_at": e.created_at.isoformat(),
            }
            for e in qs
        ]
        return Response({"count": len(events), "results": events}, status=status.HTTP_200_OK)


class PaperTradingView(APIView):
    """
    GET  /api/strategies/paper/ — Carteras de paper trading del usuario.
    POST /api/strategies/paper/ — Lanza una cartera virtual que sigue una
         estrategia generada. Body: {"strategy_id": int, "initial_capital"?: float}.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.application.use_cases.paper_trading import PaperTradingListUseCase

        return Response(
            PaperTradingListUseCase().execute(owner=request.user), status=status.HTTP_200_OK,
        )

    def post(self, request):
        from core.infrastructure.persistence.models import PaperTradingAccount, StrategyDefinition

        strategy_id = request.data.get("strategy_id")
        if not strategy_id:
            return Response({"error": "Falta strategy_id."}, status=status.HTTP_400_BAD_REQUEST)
        strat = StrategyDefinition.objects.select_related("asset").filter(id=strategy_id).first()
        if strat is None:
            return Response({"error": "Estrategia no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        if not strat.asset:
            return Response({"error": "La estrategia no tiene activo asociado."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            capital = float(request.data.get("initial_capital", 10000.0))
        except (TypeError, ValueError):
            capital = 10000.0
        capital = min(max(capital, 100.0), 1_000_000.0)

        # Reactivar si el usuario ya seguía esta estrategia (evita duplicados).
        existing = PaperTradingAccount.objects.filter(
            owner=request.user, strategy=strat, is_active=True,
        ).first()
        if existing:
            from core.application.use_cases.paper_trading import _serialize_account
            return Response(_serialize_account(existing), status=status.HTTP_200_OK)

        acc = PaperTradingAccount.objects.create(
            strategy=strat, owner=request.user,
            asset_symbol=strat.asset.symbol, interval=strat.interval,
            initial_capital=capital, cash=capital,
        )
        from core.application.use_cases.paper_trading import _serialize_account
        return Response(_serialize_account(acc), status=status.HTTP_201_CREATED)


class PaperTradingDetailView(APIView):
    """
    GET    /api/strategies/paper/<id>/ — Detalle de una cartera con su historial.
    DELETE /api/strategies/paper/<id>/ — Detiene la cartera (deja de operar).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, account_id: int):
        from core.application.use_cases.paper_trading import PaperTradingDetailUseCase

        data = PaperTradingDetailUseCase().execute(owner=request.user, account_id=account_id)
        if data is None:
            return Response({"error": "Cartera no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        return Response(data, status=status.HTTP_200_OK)

    def delete(self, request, account_id: int):
        from core.infrastructure.persistence.models import PaperTradingAccount

        acc = PaperTradingAccount.objects.filter(id=account_id, owner=request.user).first()
        if acc is None:
            return Response({"error": "Cartera no encontrada."}, status=status.HTTP_404_NOT_FOUND)
        acc.is_active = False
        acc.save(update_fields=["is_active", "updated_at"])
        return Response({"id": acc.id, "is_active": False}, status=status.HTTP_200_OK)


class StrategyPortfolioView(APIView):
    """
    GET /api/strategies/portfolio/?top=5 — Análisis de cartera de las estrategias
    campeonas: matriz de correlación entre sus retornos diarios, correlación
    media y métricas de la cartera equiponderada (equity, retorno, drawdown,
    Sharpe) sobre la ventana común de datos.
    """
    permission_classes = [IsAuthenticated]
    _CACHE_TTL = 900  # segundos — re-ejecuta hasta 6 backtests

    def get(self, request):
        from core.application.use_cases.strategy_portfolio import StrategyPortfolioUseCase

        try:
            top = min(max(int(request.query_params.get("top", 5)), 2), 6)
        except (TypeError, ValueError):
            top = 5

        cache_key = f"strategy_portfolio:{top}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached, status=status.HTTP_200_OK)

        result = StrategyPortfolioUseCase().execute(top_n=top)
        if result.get("error"):
            return Response(result, status=status.HTTP_200_OK)
        cache.set(cache_key, result, self._CACHE_TTL)
        return Response(result, status=status.HTTP_200_OK)


class BestStrategiesView(APIView):
    """
    GET /api/strategies/best/ — Mejor estrategia validada de cada activo (la
    campeona por fitness), con su rendimiento en holdout y su track record en
    vivo (paper trading del usuario). Filtro opcional: ?interval=1d.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.application.use_cases.reoptimize_strategies import BestStrategiesUseCase

        interval = request.query_params.get("interval")
        return Response(
            BestStrategiesUseCase().execute(owner=request.user, interval=interval),
            status=status.HTTP_200_OK,
        )


class TradingConnectionsView(APIView):
    """
    GET  /api/trading/connections/ — Conexiones de exchange del usuario (sin
         credenciales: nunca se devuelven).
    POST /api/trading/connections/ — Conecta un exchange. Body: {"exchange",
         "api_key", "api_secret", "api_password"?, "is_testnet"?, "label"?}.
         Se verifica contra el exchange antes de guardarse (cifrada).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.application.use_cases.broker_trading import ListConnectionsUseCase

        return Response(ListConnectionsUseCase().execute(owner=request.user), status=status.HTTP_200_OK)

    def post(self, request):
        from core.application.use_cases.broker_trading import ConnectExchangeUseCase

        result = ConnectExchangeUseCase().execute(
            owner=request.user,
            exchange=request.data.get("exchange", ""),
            api_key=request.data.get("api_key", ""),
            api_secret=request.data.get("api_secret", ""),
            api_password=request.data.get("api_password", ""),
            is_testnet=bool(request.data.get("is_testnet", True)),
            label=request.data.get("label", ""),
        )
        if result.get("error"):
            return Response(result, status=status.HTTP_400_BAD_REQUEST)
        return Response(result, status=status.HTTP_201_CREATED)


class TradingConnectionDetailView(APIView):
    """DELETE /api/trading/connections/<id>/ — Desconecta el exchange."""
    permission_classes = [IsAuthenticated]

    def delete(self, request, connection_id: int):
        from core.application.use_cases.broker_trading import RemoveConnectionUseCase

        result = RemoveConnectionUseCase().execute(owner=request.user, connection_id=connection_id)
        if result.get("error"):
            return Response(result, status=status.HTTP_404_NOT_FOUND)
        return Response(result, status=status.HTTP_200_OK)


class TradingBalanceView(APIView):
    """GET /api/trading/connections/<id>/balance/ — Saldos de la conexión."""
    permission_classes = [IsAuthenticated]

    def get(self, request, connection_id: int):
        from core.application.use_cases.broker_trading import GetBrokerBalanceUseCase

        result = GetBrokerBalanceUseCase().execute(owner=request.user, connection_id=connection_id)
        if result.get("error"):
            code = status.HTTP_404_NOT_FOUND if "no encontrada" in result["error"] else status.HTTP_400_BAD_REQUEST
            return Response(result, status=code)
        return Response(result, status=status.HTTP_200_OK)


class TradingOrdersView(APIView):
    """
    GET  /api/trading/connections/<id>/orders/?symbol= — Órdenes abiertas.
    POST /api/trading/connections/<id>/orders/ — Lanza una orden manual.
         Body: {"symbol": "BTC/USDT", "side": "buy|sell", "type": "market|limit",
                "amount": float, "price"?: float}.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, connection_id: int):
        from core.application.use_cases.broker_trading import OpenOrdersUseCase

        result = OpenOrdersUseCase().execute(
            owner=request.user, connection_id=connection_id,
            symbol=request.query_params.get("symbol"),
        )
        if result.get("error"):
            code = status.HTTP_404_NOT_FOUND if "no encontrada" in result["error"] else status.HTTP_400_BAD_REQUEST
            return Response(result, status=code)
        return Response(result, status=status.HTTP_200_OK)

    def post(self, request, connection_id: int):
        from core.application.use_cases.broker_trading import PlaceOrderUseCase

        result = PlaceOrderUseCase().execute(
            owner=request.user,
            connection_id=connection_id,
            symbol=request.data.get("symbol", ""),
            side=request.data.get("side", ""),
            order_type=request.data.get("type", ""),
            amount=request.data.get("amount"),
            price=request.data.get("price"),
        )
        if result.get("error"):
            code = status.HTTP_404_NOT_FOUND if "no encontrada" in result["error"] else status.HTTP_400_BAD_REQUEST
            return Response(result, status=code)
        return Response(result, status=status.HTTP_201_CREATED)


class TradingCancelOrderView(APIView):
    """POST /api/trading/connections/<id>/orders/cancel/ — Cancela una orden.
    Body: {"order_id", "symbol"}."""
    permission_classes = [IsAuthenticated]

    def post(self, request, connection_id: int):
        from core.application.use_cases.broker_trading import CancelOrderUseCase

        result = CancelOrderUseCase().execute(
            owner=request.user, connection_id=connection_id,
            order_id=str(request.data.get("order_id", "")),
            symbol=request.data.get("symbol", ""),
        )
        if result.get("error"):
            code = status.HTTP_404_NOT_FOUND if "no encontrada" in result["error"] else status.HTTP_400_BAD_REQUEST
            return Response(result, status=code)
        return Response(result, status=status.HTTP_200_OK)


class AssetDetailInfoView(APIView):
    """
    GET /api/assets/<symbol>/info/ — Información de proyecto de un activo.

    Consolida desde CoinGecko: enlaces (web, whitepaper, twitter, reddit),
    datos de mercado (ATH, suministro) y categorías.
    Requiere autenticación JWT.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, symbol: str):
        from core.infrastructure.external_apis.coingecko_client import (
            CoinGeckoClient,
            CoinGeckoClientError,
        )

        symbol = symbol.upper()
        asset = CryptoAssetModel.objects.filter(symbol=symbol).values("coingecko_id").first()
        if not asset or not asset["coingecko_id"]:
            return Response(
                {"error": f"Activo {symbol} no encontrado o sin coingecko_id."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            data = CoinGeckoClient().get_coin_detail(asset["coingecko_id"])
        except CoinGeckoClientError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        links = data.get("links", {})
        market = data.get("market_data", {})

        homepage = next(
            (u for u in links.get("homepage", []) if u), None
        )
        whitepaper = links.get("whitepaper") or None
        twitter_handle = links.get("twitter_screen_name") or None
        twitter = f"https://twitter.com/{twitter_handle}" if twitter_handle else None
        reddit = links.get("subreddit_url") or None
        telegram_id = links.get("telegram_channel_identifier") or None
        telegram = f"https://t.me/{telegram_id}" if telegram_id else None
        github_repos = (links.get("repos_url") or {}).get("github") or []
        github = next((u for u in github_repos if u), None)

        ath = (market.get("ath") or {}).get("usd")
        ath_date_raw = (market.get("ath_date") or {}).get("usd")
        ath_date = ath_date_raw[:10] if ath_date_raw else None
        circulating_supply = market.get("circulating_supply")
        max_supply = market.get("max_supply")

        categories = [c for c in data.get("categories", []) if c][:5]
        description = (data.get("description") or {}).get("en") or None

        return Response({
            "homepage": homepage,
            "whitepaper": whitepaper,
            "twitter": twitter,
            "reddit": reddit,
            "telegram": telegram,
            "github": github,
            "ath": ath,
            "ath_date": ath_date,
            "circulating_supply": circulating_supply,
            "max_supply": max_supply,
            "categories": categories,
            "description": description,
        }, status=status.HTTP_200_OK)



class AvailableStrategiesView(APIView):
    """
    GET /api/analysis/strategies/ — Lista estrategias disponibles para backtesting.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        strategies = RunBacktestUseCase.get_available_strategies()
        return Response(strategies, status=status.HTTP_200_OK)


# ── Portfolio Views ────────────────────────────────────────────────

class PortfolioView(APIView):
    """
    GET  /api/portfolio/  — Resumen del portfolio con PnL calculado.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        summary = GetPortfolioUseCase().execute(request.user)
        positions_data = [vars(p) for p in summary.positions]
        return Response(
            {
                "total_invested_usd": summary.total_invested_usd,
                "total_current_value_usd": summary.total_current_value_usd,
                "total_pnl_usd": summary.total_pnl_usd,
                "total_pnl_pct": summary.total_pnl_pct,
                "is_profit": summary.is_profit,
                "long_count": summary.long_count,
                "short_count": summary.short_count,
                "total_long_invested_usd": summary.total_long_invested_usd,
                "total_short_exposure_usd": summary.total_short_exposure_usd,
                "positions": PortfolioPositionSerializer(positions_data, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class TradeListView(APIView):
    """
    GET  /api/portfolio/trades/  — Listar historial de operaciones.
    POST /api/portfolio/trades/  — Registrar nueva operación.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query_ser = TradeHistoryQuerySerializer(data=request.query_params)
        if not query_ser.is_valid():
            return Response(query_ser.errors, status=status.HTTP_400_BAD_REQUEST)
        q = query_ser.validated_data

        trades = GetTradeHistoryUseCase().execute(
            user=request.user,
            symbol=q.get("symbol", ""),
            trade_type=q.get("trade_type", ""),
            limit=q.get("limit", 50),
        )
        return Response(
            TradeOutputSerializer([vars(t) for t in trades], many=True).data,
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = AddTradeSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        v = serializer.validated_data
        try:
            trade = AddTradeUseCase().execute(
                user=request.user,
                dto=AddTradeInputDTO(
                    asset_symbol=v["asset_symbol"],
                    trade_type=v["trade_type"],
                    quantity=float(v["quantity"]),
                    price_usd=float(v["price_usd"]),
                    executed_at=v["executed_at"].isoformat(),
                    notes=v.get("notes", ""),
                ),
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            TradeOutputSerializer(vars(trade)).data,
            status=status.HTTP_201_CREATED,
        )


class TradeDetailView(APIView):
    """
    DELETE /api/portfolio/trades/<trade_id>/  — Eliminar una operación.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, trade_id: int):
        try:
            DeleteTradeUseCase().execute(user=request.user, trade_id=trade_id)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Alerts Views ───────────────────────────────────────────────────

class AlertListView(APIView):
    """
    GET  /api/alerts/  — Listar todas las alertas del usuario.
    POST /api/alerts/  — Crear nueva alerta de precio.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        active_only = request.query_params.get("active_only", "false").lower() == "true"
        alerts = ListAlertsUseCase().execute(request.user, active_only=active_only)
        return Response(
            AlertOutputSerializer([vars(a) for a in alerts], many=True).data,
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = CreateAlertSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        v = serializer.validated_data
        try:
            alert = CreateAlertUseCase().execute(
                user=request.user,
                dto=CreateAlertInputDTO(
                    asset_symbol=v["asset_symbol"],
                    condition=v["condition"],
                    threshold_price=float(v["threshold_price"]),
                    notes=v.get("notes", ""),
                ),
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            AlertOutputSerializer(vars(alert)).data,
            status=status.HTTP_201_CREATED,
        )


class AlertDetailView(APIView):
    """
    DELETE /api/alerts/<alert_id>/  — Eliminar una alerta.
    PATCH  /api/alerts/<alert_id>/toggle/  — Activar/desactivar.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, alert_id: int):
        try:
            DeleteAlertUseCase().execute(user=request.user, alert_id=alert_id)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AlertToggleView(APIView):
    """
    PATCH /api/alerts/<alert_id>/toggle/ — Activar/desactivar una alerta.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, alert_id: int):
        try:
            alert = ToggleAlertUseCase().execute(user=request.user, alert_id=alert_id)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_404_NOT_FOUND)
        return Response(
            AlertOutputSerializer(vars(alert)).data,
            status=status.HTTP_200_OK,
        )


# ── Positions (modelo explícito) ──────────────────────────────────────────────

class PositionListView(APIView):
    """
    GET  /api/portfolio/positions/  — Listar posiciones (filtrar por ?status=OPEN|CLOSED).
    POST /api/portfolio/positions/  — Abrir una nueva posición LONG o SHORT.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query_ser = PositionsQuerySerializer(data=request.query_params)
        if not query_ser.is_valid():
            return Response(query_ser.errors, status=status.HTTP_400_BAD_REQUEST)

        status_filter = query_ser.validated_data.get("status") or None
        summary = GetPositionsUseCase().execute(user=request.user, status=status_filter)

        return Response(
            PositionSummaryOutputSerializer(vars(summary)).data,
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = OpenPositionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        v = serializer.validated_data
        try:
            position = OpenPositionUseCase().execute(
                user=request.user,
                dto=OpenPositionInputDTO(
                    asset_symbol=v["asset_symbol"],
                    direction=v["direction"],
                    quantity=float(v["quantity"]),
                    entry_price=float(v["entry_price"]),
                    opened_at=v["opened_at"].isoformat(),
                    label=v.get("label", ""),
                    notes=v.get("notes", ""),
                ),
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            PositionOutputSerializer(vars(position)).data,
            status=status.HTTP_201_CREATED,
        )


class PositionDetailView(APIView):
    """
    PATCH  /api/portfolio/positions/<position_id>/  — Actualizar label.
    DELETE /api/portfolio/positions/<position_id>/  — Eliminar (sólo sin trades).
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, position_id: int):
        serializer = UpdatePositionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            pos = PositionModel.objects.get(pk=position_id, user=request.user)
        except PositionModel.DoesNotExist:
            return Response({"error": "Posición no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        pos.label = serializer.validated_data["label"]
        pos.save(update_fields=["label", "updated_at"])

        from core.application.use_cases.open_position import _build_position_dto
        from decimal import Decimal
        current_price = Decimal(str(pos.asset.current_price or pos.avg_entry_price))
        dto = _build_position_dto(pos, current_price)
        return Response(PositionOutputSerializer(vars(dto)).data, status=status.HTTP_200_OK)

    def delete(self, request, position_id: int):
        try:
            pos = PositionModel.objects.get(pk=position_id, user=request.user)
        except PositionModel.DoesNotExist:
            return Response({"error": "Posición no encontrada."}, status=status.HTTP_404_NOT_FOUND)

        if pos.trades.exists():
            return Response(
                {"error": "No se puede eliminar una posición que ya tiene trades asociados."},
                status=status.HTTP_409_CONFLICT,
            )
        pos.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PositionAddView(APIView):
    """
    POST /api/portfolio/positions/<position_id>/add/ — Ampliar posición (escalar entrada, AVCO).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, position_id: int):
        serializer = AddToPositionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        v = serializer.validated_data
        try:
            position = ScalePositionUseCase().execute(
                user=request.user,
                position_id=position_id,
                dto=AddToPositionInputDTO(
                    quantity=float(v["quantity"]),
                    entry_price=float(v["entry_price"]),
                    executed_at=v["executed_at"].isoformat(),
                    notes=v.get("notes", ""),
                ),
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            PositionOutputSerializer(vars(position)).data,
            status=status.HTTP_200_OK,
        )


class PositionCloseView(APIView):
    """
    POST /api/portfolio/positions/<position_id>/close/ — Cerrar posición parcial o totalmente.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, position_id: int):
        serializer = ClosePositionSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        v = serializer.validated_data
        try:
            position = ClosePositionUseCase().execute(
                user=request.user,
                position_id=position_id,
                dto=ClosePositionInputDTO(
                    close_quantity=float(v["close_quantity"]),
                    close_price=float(v["close_price"]),
                    executed_at=v["executed_at"].isoformat(),
                    notes=v.get("notes", ""),
                ),
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            PositionOutputSerializer(vars(position)).data,
            status=status.HTTP_200_OK,
        )


# ── Watchlist ─────────────────────────────────────────────────────────────────

class WatchlistView(APIView):
    """
    GET  /api/watchlist/  — Listar los activos en la watchlist del usuario.
    POST /api/watchlist/  — Añadir un activo a la watchlist del usuario.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        entries = (
            UserWatchlistModel.objects
            .filter(user=request.user)
            .select_related("asset")
            .order_by("-added_at")
        )
        data = [
            {
                "symbol": e.asset.symbol,
                "name": e.asset.name,
                "logo_url": e.asset.logo_url,
                "current_price": str(e.asset.current_price) if e.asset.current_price is not None else "0",
                "price_change_24h": str(e.asset.price_change_24h) if e.asset.price_change_24h is not None else "0",
                "is_bullish_24h": float(e.asset.price_change_24h or 0) >= 0,
                "added_at": e.added_at.isoformat(),
            }
            for e in entries
        ]
        return Response(
            WatchlistItemSerializer(data, many=True).data,
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = WatchlistAddSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        symbol = serializer.validated_data["symbol"].upper()
        try:
            asset = CryptoAssetModel.objects.get(symbol=symbol)
        except CryptoAssetModel.DoesNotExist:
            return Response({"error": f"Activo '{symbol}' no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        _, created = UserWatchlistModel.objects.get_or_create(
            user=request.user,
            asset=asset,
        )
        if not created:
            return Response({"detail": "El activo ya está en la watchlist."}, status=status.HTTP_200_OK)

        return Response({"detail": f"{symbol} añadido a la watchlist."}, status=status.HTTP_201_CREATED)


class WatchlistItemView(APIView):
    """
    DELETE /api/watchlist/<symbol>/  — Eliminar un activo de la watchlist del usuario.
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request, symbol: str):
        deleted, _ = UserWatchlistModel.objects.filter(
            user=request.user,
            asset__symbol=symbol.upper(),
        ).delete()
        if not deleted:
            return Response({"error": "El activo no está en la watchlist."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)
