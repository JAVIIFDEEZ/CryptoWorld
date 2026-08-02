"""
interfaces/api/views.py — Controladores HTTP (DRF Views).

Esta es la única capa que sabe de HTTP.
Responsabilidades:
  1. Recibir y validar la petición HTTP (usando serializers)
  2. Construir el DTO de entrada
  3. Invocar el caso de uso correspondiente (capa application)
  4. Serializar el DTO de salida → respuesta HTTP

Lo que las views NUNCA deben hacer:
  - Lógica de negocio
  - Consultas directas a la base de datos
  - Operaciones matemáticas o financieras

Principio aplicado: Single Responsibility + Clean Architecture.
"""

import logging

from django.conf import settings
from django.contrib.auth import authenticate
from django.core.cache import cache
from django.db import transaction
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.application.dto.alerts_dto import CreateAlertInputDTO
from core.application.dto.asset_dto import (
    AnalysisRequestInputDTO,
    BacktestRequestDTO,
    PatternsRequestDTO,
    PredictionRequestDTO,
    SignalsRequestDTO,
)
from core.application.dto.auth_dto import (
    ChangePasswordDTO,
    Disable2FADTO,
    Enable2FADTO,
    LogoutInputDTO,
    PasswordResetConfirmDTO,
    RegisterUserInputDTO,
    Verify2FALoginDTO,
    VerifyEmailInputDTO,
)
from core.application.dto.portfolio_dto import (
    AddToPositionInputDTO,
    AddTradeInputDTO,
    ClosePositionInputDTO,
    OpenPositionInputDTO,
)
from core.application.services import audit
from core.application.services.login_guard import (
    PASSWORD_POLICY,
    TOTP_POLICY,
    AccountLockedError,
    ensure_not_locked,
    register_failure,
)
from core.application.services.login_guard import (
    reset as reset_login_attempts,
)
from core.application.services.sessions import build_refresh_token
from core.application.use_cases.add_trade import AddTradeUseCase
from core.application.use_cases.change_password import ChangePasswordUseCase
from core.application.use_cases.close_position import ClosePositionUseCase
from core.application.use_cases.confirm_password_reset import ConfirmPasswordResetUseCase
from core.application.use_cases.delete_trade import DeleteTradeUseCase
from core.application.use_cases.delete_user_account import DeleteUserAccountUseCase
from core.application.use_cases.detect_patterns import DetectPatternsUseCase
from core.application.use_cases.disable_2fa import Disable2FAUseCase
from core.application.use_cases.enable_2fa import Enable2FAUseCase
from core.application.use_cases.get_asset_ohlcv import GetAssetOhlcvUseCase
from core.application.use_cases.get_assets import GetAssetsUseCase
from core.application.use_cases.get_market_overview import GetMarketOverviewUseCase
from core.application.use_cases.get_multichain_stats import GetMultiChainStatsUseCase
from core.application.use_cases.get_news_feed import GetNewsFeedUseCase
from core.application.use_cases.get_onchain_metrics import GetOnChainMetricsUseCase
from core.application.use_cases.get_portfolio import GetPortfolioUseCase
from core.application.use_cases.get_positions import GetPositionsUseCase
from core.application.use_cases.get_signals_dashboard import GetSignalsDashboardUseCase
from core.application.use_cases.get_trade_history import GetTradeHistoryUseCase
from core.application.use_cases.logout import LogoutUseCase
from core.application.use_cases.manage_alerts import (
    CreateAlertUseCase,
    DeleteAlertUseCase,
    ListAlertsUseCase,
    ToggleAlertUseCase,
)
from core.application.use_cases.open_position import OpenPositionUseCase
from core.application.use_cases.predict_price import PredictPriceUseCase
from core.application.use_cases.register_user import RegisterUserUseCase
from core.application.use_cases.run_analysis import RunAnalysisUseCase
from core.application.use_cases.run_backtest import RunBacktestUseCase
from core.application.use_cases.scale_position import ScalePositionUseCase
from core.application.use_cases.setup_2fa import Setup2FAUseCase
from core.application.use_cases.verify_2fa_login import PreAuthToken, Verify2FALoginUseCase
from core.application.use_cases.verify_email import VerifyEmailUseCase
from core.domain.services.user_domain_service import UserDomainService
from core.infrastructure.persistence.models import AuditLog
from core.infrastructure.persistence.models import CryptoAsset as CryptoAssetModel
from core.infrastructure.persistence.models import MarketDataSnapshot as MarketDataSnapshotModel
from core.infrastructure.persistence.models import Position as PositionModel
from core.infrastructure.persistence.models import User as UserModel
from core.infrastructure.persistence.models import UserWatchlist as UserWatchlistModel
from core.infrastructure.persistence.repositories_impl import (
    DjangoCryptoAssetRepository,
    DjangoUserRepository,
)
from core.interfaces.api.authentication import CredentialEpochJWTAuthentication
from core.interfaces.api.exception_handler import DomainError
from core.interfaces.api.serializers import (
    AddToPositionSerializer,
    AddTradeSerializer,
    AlertOutputSerializer,
    AnalysisOutputSerializer,
    AnalysisRequestSerializer,
    BacktestRequestSerializer,
    CalculateAnalysisSerializer,
    ChangeEmailConfirmSerializer,
    ChangeEmailRequestSerializer,
    ChangePasswordSerializer,
    ClosePositionSerializer,
    CreateAlertSerializer,
    CryptoAssetSerializer,
    DeleteAccountSerializer,
    Disable2FASerializer,
    Enable2FASerializer,
    LoginSerializer,
    LogoutSerializer,
    MarketOverviewSerializer,
    NewsItemSerializer,
    NewsQuerySerializer,
    OhlcvCandleSerializer,
    OhlcvQuerySerializer,
    OnChainQuerySerializer,
    OpenPositionSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    PatternsRequestSerializer,
    PortfolioPositionSerializer,
    PositionOutputSerializer,
    PositionsQuerySerializer,
    PositionSummaryOutputSerializer,
    PredictionRequestSerializer,
    RegisterSerializer,
    ResendVerificationRequestSerializer,
    SignalsRequestSerializer,
    TradeHistoryQuerySerializer,
    TradeOutputSerializer,
    UpdatePositionSerializer,
    UpdatePreferencesSerializer,
    Verify2FALoginSerializer,
    VerifyEmailSerializer,
    WatchlistAddSerializer,
    WatchlistItemSerializer,
)
from core.tasks import dispatch_task
from core.tasks import send_password_reset_email as send_password_reset_email_task
from core.tasks import send_verification_email as send_verification_email_task

logger = logging.getLogger(__name__)

# Versión del servicio publicada en las sondas de salud. Se lee del
# entorno para que coincida con la imagen desplegada en lugar de quedar
# congelada en el código (antes estaba fijada a "1.0.0").
APP_VERSION = getattr(settings, "APP_VERSION", "1.139.0")


# ── Health Check ───────────────────────────────────────────────────

class LivenessView(APIView):
    """
    GET /api/health/live/ — Sonda de vitalidad (liveness probe).

    Responde 200 si el proceso web atiende peticiones, sin tocar ninguna
    dependencia. Es lo que debe consultar el orquestador para decidir si
    reinicia el contenedor: si sondease Redis o la base de datos, un
    parpadeo de una dependencia externa provocaría un reinicio en bucle
    del servicio web, que es justo lo contrario de lo que se busca.
    """

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    @extend_schema(
        summary="Sonda de vitalidad",
        responses={200: OpenApiResponse(description="El proceso web responde.")},
        tags=["Salud"],
    )
    def get(self, request):
        return Response(
            {"status": "ok", "service": "CryptoWorld API", "version": APP_VERSION},
            status=status.HTTP_200_OK,
        )


class ReadinessView(APIView):
    """
    GET /api/health/  — Sonda de disponibilidad (readiness probe).

    Sondea las dependencias críticas (base de datos, cache Redis y broker
    de Celery) y responde 200 si todas están sanas o 503 si alguna falla,
    para que el balanceador deje de enviar tráfico a una réplica que no
    puede servirlo.

    El detalle por componente solo se revela a administradores: para el
    resto es un dato de arquitectura interna que no aporta al cliente y
    sí ayuda a quien esté haciendo reconocimiento del sistema.
    """

    permission_classes = [AllowAny]
    authentication_classes = [CredentialEpochJWTAuthentication]
    throttle_classes = []

    @staticmethod
    def _check_components() -> dict:
        from django.conf import settings as dj_settings
        from django.db import connection
        from kombu import Connection as BrokerConnection

        components = {}

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            components["database"] = "ok"
        except Exception:
            logger.warning("Healthcheck: base de datos inaccesible", exc_info=True)
            components["database"] = "error"

        try:
            cache.set("health_ping", "1", 5)
            components["cache"] = "ok" if cache.get("health_ping") == "1" else "error"
        except Exception:
            logger.warning("Healthcheck: cache inaccesible", exc_info=True)
            components["cache"] = "error"

        try:
            with BrokerConnection(dj_settings.CELERY_BROKER_URL, connect_timeout=2) as conn:
                conn.ensure_connection(max_retries=0)
            components["celery_broker"] = "ok"
        except Exception:
            logger.warning("Healthcheck: broker Celery inaccesible", exc_info=True)
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

    @extend_schema(
        summary="Sonda de disponibilidad",
        responses={
            200: OpenApiResponse(description="Todas las dependencias responden."),
            503: OpenApiResponse(description="Alguna dependencia crítica falla."),
        },
        tags=["Salud"],
    )
    def get(self, request):
        components = self._check_components()
        checks = {k: v for k, v in components.items() if k != "email_backend"}
        healthy = all(v == "ok" for v in checks.values())

        body = {
            "status": "ok" if healthy else "degraded",
            "version": APP_VERSION,
            "service": "CryptoWorld API",
        }

        # El desglose de dependencias es información de infraestructura.
        if request.user.is_authenticated and request.user.is_staff:
            body["components"] = components

        return Response(
            body,
            status=status.HTTP_200_OK if healthy else status.HTTP_503_SERVICE_UNAVAILABLE,
        )


# ── Auth Views ─────────────────────────────────────────────────────

class RegisterView(APIView):
    """
    POST /api/auth/register — Registrar un nuevo usuario.

    Flujo:
      1. Validar datos de entrada con RegisterSerializer
      2. Construir DTO de entrada
      3. Delegar al caso de uso RegisterUserUseCase
      4. Enviar email de verificación
      5. Devolver respuesta 201 con datos del usuario creado
    """
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_register"

    @extend_schema(
        summary="Registrar un nuevo usuario",
        request=RegisterSerializer,
        responses={
            201: OpenApiResponse(description="Cuenta creada; email de verificación enviado."),
            400: OpenApiResponse(description="Datos inválidos o email/usuario ya en uso."),
        },
        tags=["Autenticación"],
    )
    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated = serializer.validated_data

        user_repo = DjangoUserRepository()
        user_domain_service = UserDomainService(user_repo)
        use_case = RegisterUserUseCase(user_repo, user_domain_service)

        input_dto = RegisterUserInputDTO(
            email=validated["email"],
            username=validated["username"],
            password=validated["password"],
        )

        # Atómico: el alta y el establecimiento de la contraseña son una
        # sola operación. Sin la transacción, un fallo entre ambos pasos
        # dejaba un usuario con el email ocupado y sin contraseña válida,
        # imposible de recuperar y de volver a registrar.
        with transaction.atomic():
            output_dto = use_case.execute(input_dto)
            user_repo.set_password(output_dto.id, validated["password"])

        # Fuera de la transacción: encolar el email solo tiene sentido si
        # el alta ya está confirmada en la base de datos.
        dispatch_task(send_verification_email_task, output_dto.id)

        audit.record(
            AuditLog.Action.REGISTER,
            request=request,
            actor_email=output_dto.email,
            target_type="user",
            target_id=output_dto.id,
        )

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
    POST /api/auth/login — Autenticar usuario y devolver tokens JWT.

    Si el usuario tiene 2FA activo, devuelve un token temporal (pre_auth_token)
    en lugar de los tokens completos. El cliente debe completar el segundo factor
    en POST /api/auth/2fa/login/.
    """
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_login"

    @extend_schema(
        summary="Iniciar sesión",
        request=LoginSerializer,
        responses={
            200: OpenApiResponse(description="Tokens JWT, o pre_auth_token si hay 2FA."),
            401: OpenApiResponse(description="Credenciales inválidas."),
            403: OpenApiResponse(description="Cuenta desactivada o email sin verificar."),
            429: OpenApiResponse(description="Cuenta bloqueada por intentos fallidos."),
        },
        tags=["Autenticación"],
    )
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated = serializer.validated_data
        # El email es el identificador de login: se normaliza igual que en
        # el registro para que las mayúsculas no partan ni la cuenta ni el
        # contador de intentos fallidos.
        email = validated["email"].strip().lower()

        # El límite por IP no protege de una botnet repartiendo intentos
        # contra una sola cuenta: este guardia cuenta por cuenta.
        try:
            ensure_not_locked(PASSWORD_POLICY, email)
        except AccountLockedError as exc:
            audit.record(
                AuditLog.Action.LOGIN_BLOCKED,
                request=request,
                actor_email=email,
                outcome=AuditLog.Outcome.FAILURE,
            )
            raise DomainError(
                str(exc),
                code="account_locked",
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            ) from exc

        user = authenticate(request, username=email, password=validated["password"])

        if user is None:
            attempts = register_failure(PASSWORD_POLICY, email)
            audit.record(
                AuditLog.Action.LOGIN_FAILURE,
                request=request,
                actor_email=email,
                outcome=AuditLog.Outcome.FAILURE,
                failed_attempts=attempts,
            )
            # Mensaje deliberadamente idéntico exista o no la cuenta, para
            # no convertir el login en un oráculo de emails registrados.
            raise DomainError(
                "Credenciales inválidas.",
                code="invalid_credentials",
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        # Credenciales correctas: el contador se limpia aquí y no más
        # abajo, para que una cuenta desactivada o sin verificar no quede
        # acumulando intentos "fallidos" que no lo son.
        reset_login_attempts(PASSWORD_POLICY, email)

        if not user.is_active:
            audit.record(
                AuditLog.Action.LOGIN_FAILURE,
                request=request,
                actor=user,
                outcome=AuditLog.Outcome.FAILURE,
                reason="account_disabled",
            )
            raise DomainError(
                "Cuenta desactivada.",
                code="account_disabled",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # Política de seguridad: no permitir login hasta verificar email
        if not user.is_email_verified:
            audit.record(
                AuditLog.Action.LOGIN_FAILURE,
                request=request,
                actor=user,
                outcome=AuditLog.Outcome.FAILURE,
                reason="email_not_verified",
            )
            raise DomainError(
                "Debes verificar tu email antes de iniciar sesión.",
                code="email_not_verified",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        # Si 2FA está activo, emitir token temporal de pre-autenticación
        if user.is_2fa_enabled:
            audit.record(
                AuditLog.Action.TWO_FACTOR_CHALLENGE, request=request, actor=user
            )
            pre_auth = PreAuthToken()
            pre_auth["user_id"] = user.pk
            return Response(
                {
                    "requires_2fa": True,
                    "pre_auth_token": str(pre_auth),
                },
                status=status.HTTP_200_OK,
            )

        # Sin 2FA: emitir tokens completos. `build_refresh_token` añade el
        # claim de revocación que la autenticación comprueba después.
        refresh = build_refresh_token(user)
        audit.record(AuditLog.Action.LOGIN_SUCCESS, request=request, actor=user)

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
    POST /api/auth/logout/ — Cerrar sesión añadiendo el refresh_token a la blacklist.
    No requiere access token válido: el propio refresh_token es prueba suficiente.
    Esto permite hacer logout aunque el access token ya haya expirado.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Cerrar sesión",
        request=LogoutSerializer,
        responses={200: OpenApiResponse(description="Refresh token invalidado.")},
        tags=["Autenticación"],
    )
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        LogoutUseCase().execute(
            LogoutInputDTO(refresh_token=serializer.validated_data["refresh_token"])
        )

        audit.record(
            AuditLog.Action.LOGOUT,
            request=request,
            actor=request.user if request.user.is_authenticated else None,
        )

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

    @extend_schema(
        summary="Perfil del usuario autenticado",
        tags=["Cuenta"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def get(self, request):
        return Response(self._serialize(request.user), status=status.HTTP_200_OK)

    @extend_schema(
        summary="Actualizar perfil y preferencias",
        request=UpdatePreferencesSerializer,
        tags=["Cuenta"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def patch(self, request):
        serializer = UpdatePreferencesSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

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
            raise DomainError(
                "El nombre de usuario ya está en uso.", code="username_taken"
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

    @extend_schema(
        summary="Solicitar cambio de email",
        request=ChangeEmailRequestSerializer,
        tags=["Cuenta"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request):
        from core.application.use_cases.change_email import RequestEmailChangeUseCase
        from core.tasks import send_email_change_email as send_email_change_task

        serializer = ChangeEmailRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        v = serializer.validated_data
        RequestEmailChangeUseCase().execute(
            user_id=request.user.pk,
            new_email=v["new_email"],
            password=v["password"],
        )

        dispatch_task(send_email_change_task, request.user.pk)

        audit.record(
            AuditLog.Action.EMAIL_CHANGE_REQUESTED,
            request=request,
            actor=request.user,
            target_type="user",
            target_id=request.user.pk,
        )

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

    @extend_schema(
        summary="Confirmar cambio de email",
        request=ChangeEmailConfirmSerializer,
        tags=["Cuenta"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request):
        from core.application.use_cases.change_email import ConfirmEmailChangeUseCase

        serializer = ChangeEmailConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = ConfirmEmailChangeUseCase().execute(serializer.validated_data["token"])

        audit.record(
            AuditLog.Action.EMAIL_CHANGED,
            request=request,
            actor=user,
            target_type="user",
            target_id=user.pk,
        )

        return Response(
            {
                "message": f"Email actualizado correctamente a {user.email}.",
                # El email es la credencial de login: al cambiarlo se
                # revocan las sesiones y el cliente debe volver a entrar.
                "sessions_revoked": True,
            },
            status=status.HTTP_200_OK,
        )


class VerifyEmailView(APIView):
    """
    GET /api/auth/verify-email/?uid=xxx&token=xxx
    Confirmar dirección de email usando el link enviado por correo.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Verificar la dirección de email",
        tags=["Cuenta"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def get(self, request):
        serializer = VerifyEmailSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        user = VerifyEmailUseCase().execute(
            VerifyEmailInputDTO(token=serializer.validated_data["token"])
        )

        audit.record(
            AuditLog.Action.EMAIL_VERIFIED,
            request=request,
            actor=user,
            target_type="user",
            target_id=user.pk,
        )

        return Response(
            {"message": "Email verificado correctamente."},
            status=status.HTTP_200_OK,
        )


class ResendVerificationEmailView(APIView):
    """
    POST /api/auth/verify-email/resend/ — Reenviar email de verificación.
    No requiere autenticación para no bloquear el flujo cuando se exige
    email verificado antes de permitir login.
    """
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_resend_verification"

    @extend_schema(
        summary="Reenviar email de verificación",
        request=ResendVerificationRequestSerializer,
        tags=["Cuenta"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request):
        serializer = ResendVerificationRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Respuesta indistinguible para evitar enumeración de emails.
        from core.infrastructure.persistence.models import User as UserModel
        user = UserModel.objects.filter(
            email__iexact=serializer.validated_data["email"]
        ).first()
        if user and not user.is_email_verified:
            dispatch_task(send_verification_email_task, user.pk)

        return Response(
            {"message": "Si el email existe y no está verificado, recibirás un enlace."},
            status=status.HTTP_200_OK,
        )


class PasswordResetRequestView(APIView):
    """
    POST /api/auth/password-reset/ — Solicitar link de recuperación por email.
    No requiere autenticación. No revela si el email existe.
    """
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_password_reset"

    @extend_schema(
        summary="Solicitar recuperación de contraseña",
        request=PasswordResetRequestSerializer,
        tags=["Cuenta"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Enviar email de forma asíncrona (no revela si el email existe)
        dispatch_task(send_password_reset_email_task, serializer.validated_data["email"])

        # Respuesta siempre igual para no revelar si el email existe
        return Response(
            {"message": "Si el email existe, recibirás un enlace de recuperación."},
            status=status.HTTP_200_OK,
        )


class PasswordResetConfirmView(APIView):
    """
    POST /api/auth/password-reset/confirm/ — Establecer nueva contraseña con el token del email.
    """
    permission_classes = [AllowAny]

    @extend_schema(
        summary="Confirmar nueva contraseña",
        request=PasswordResetConfirmSerializer,
        tags=["Cuenta"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request):
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        v = serializer.validated_data
        user = ConfirmPasswordResetUseCase().execute(
            PasswordResetConfirmDTO(
                uid=v["uid"],
                token=v["token"],
                new_password=v["new_password"],
            )
        )

        audit.record(
            AuditLog.Action.PASSWORD_RESET,
            request=request,
            actor=user,
            target_type="user",
            target_id=user.pk,
        )

        return Response(
            {
                "message": (
                    "Contraseña restablecida correctamente. Se han cerrado "
                    "todas las sesiones abiertas."
                ),
                "sessions_revoked": True,
            },
            status=status.HTTP_200_OK,
        )


class ChangePasswordView(APIView):
    """
    POST /api/auth/change-password/ — Cambiar contraseña estando autenticado.
    Requiere la contraseña actual como verificación adicional.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Cambiar la contraseña",
        request=ChangePasswordSerializer,
        tags=["Cuenta"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        v = serializer.validated_data
        tokens = ChangePasswordUseCase().execute(
            ChangePasswordDTO(
                user_id=request.user.pk,
                current_password=v["current_password"],
                new_password=v["new_password"],
            )
        )

        audit.record(
            AuditLog.Action.PASSWORD_CHANGED,
            request=request,
            actor=request.user,
            target_type="user",
            target_id=request.user.pk,
        )

        return Response(
            {
                "message": (
                    "Contraseña cambiada correctamente. Se han cerrado las "
                    "sesiones abiertas en otros dispositivos."
                ),
                # Tokens nuevos: el resto de sesiones quedan revocadas, pero
                # el dispositivo que hace el cambio continúa autenticado.
                "access_token": tokens["access_token"],
                "refresh_token": tokens["refresh_token"],
                "sessions_revoked": True,
            },
            status=status.HTTP_200_OK,
        )


# ── 2FA Views ──────────────────────────────────────────────────────

class Setup2FAView(APIView):
    """
    POST /api/auth/2fa/setup/ — Iniciar configuración de 2FA.

    Devuelve el secreto TOTP y el QR en base64 para que el usuario
    escanee con Google Authenticator / Authy.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Iniciar configuración de 2FA",
        request=None,
        tags=["Doble factor"],
        responses={200: OpenApiResponse(description="Secreto TOTP y QR en base64.")},
    )
    def post(self, request):
        output_dto = Setup2FAUseCase().execute(request.user.pk)

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
    POST /api/auth/2fa/enable/ — Activar 2FA confirmando el primer código TOTP.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Activar 2FA",
        request=Enable2FASerializer,
        tags=["Doble factor"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request):
        serializer = Enable2FASerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        recovery_codes = Enable2FAUseCase().execute(
            Enable2FADTO(
                user_id=request.user.pk,
                totp_code=serializer.validated_data["totp_code"],
            )
        )

        audit.record(
            AuditLog.Action.TWO_FACTOR_ENABLED,
            request=request,
            actor=request.user,
            target_type="user",
            target_id=request.user.pk,
        )

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
    POST /api/auth/2fa/disable/ — Desactivar 2FA (requiere código TOTP vigente).
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Desactivar 2FA",
        request=Disable2FASerializer,
        tags=["Doble factor"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request):
        serializer = Disable2FASerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        Disable2FAUseCase().execute(
            Disable2FADTO(
                user_id=request.user.pk,
                totp_code=serializer.validated_data["totp_code"],
            )
        )

        audit.record(
            AuditLog.Action.TWO_FACTOR_DISABLED,
            request=request,
            actor=request.user,
            target_type="user",
            target_id=request.user.pk,
        )

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

    @extend_schema(
        summary="Regenerar códigos de recuperación",
        request=Enable2FASerializer,
        tags=["Doble factor"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request):
        import pyotp

        from core.application.use_cases.recovery_codes import generate_recovery_codes

        serializer = Enable2FASerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        if not user.is_2fa_enabled or not user.totp_secret:
            raise DomainError("2FA no está activado en esta cuenta.", code="2fa_not_enabled")

        # El segundo factor también se protege por cuenta: son solo seis
        # dígitos y el límite por IP no frena un ataque distribuido.
        identity = f"regen:{user.pk}"
        try:
            ensure_not_locked(TOTP_POLICY, identity)
        except AccountLockedError as exc:
            raise DomainError(
                str(exc),
                code="account_locked",
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            ) from exc

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(serializer.validated_data["totp_code"], valid_window=1):
            register_failure(TOTP_POLICY, identity)
            audit.record(
                AuditLog.Action.TWO_FACTOR_FAILURE,
                request=request,
                actor=user,
                outcome=AuditLog.Outcome.FAILURE,
                reason="recovery_codes_regeneration",
            )
            raise DomainError("Código TOTP incorrecto.", code="invalid_totp")

        reset_login_attempts(TOTP_POLICY, identity)
        codes = generate_recovery_codes(user)

        audit.record(
            AuditLog.Action.RECOVERY_CODES_REGENERATED,
            request=request,
            actor=user,
            target_type="user",
            target_id=user.pk,
        )

        return Response(
            {
                "message": "Códigos de recuperación regenerados. Los anteriores ya no son válidos.",
                "recovery_codes": codes,
            },
            status=status.HTTP_200_OK,
        )


class Verify2FALoginView(APIView):
    """
    POST /api/auth/2fa/login/ — Segunda fase del login con 2FA.

    Recibe el pre_auth_token (obtenido del login normal) y el código TOTP.
    Si ambos son válidos, devuelve los tokens JWT completos.
    """
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "auth_2fa"

    @extend_schema(
        summary="Segundo paso del login con 2FA",
        request=Verify2FALoginSerializer,
        tags=["Doble factor"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request):
        serializer = Verify2FALoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        v = serializer.validated_data

        # El pre_auth_token identifica la cuenta antes de validar el
        # segundo factor: sirve para contar los intentos por cuenta, que
        # es lo que realmente frena la fuerza bruta sobre seis dígitos.
        identity = _pre_auth_identity(v["pre_auth_token"])
        try:
            ensure_not_locked(TOTP_POLICY, identity)
        except AccountLockedError as exc:
            audit.record(
                AuditLog.Action.LOGIN_BLOCKED,
                request=request,
                outcome=AuditLog.Outcome.FAILURE,
                reason="2fa_attempts",
            )
            raise DomainError(
                str(exc),
                code="account_locked",
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            ) from exc

        try:
            output_dto = Verify2FALoginUseCase().execute(
                Verify2FALoginDTO(
                    pre_auth_token=v["pre_auth_token"],
                    totp_code=v.get("totp_code", ""),
                    recovery_code=v.get("recovery_code", ""),
                )
            )
        except ValueError as exc:
            register_failure(TOTP_POLICY, identity)
            audit.record(
                AuditLog.Action.TWO_FACTOR_FAILURE,
                request=request,
                outcome=AuditLog.Outcome.FAILURE,
                target_type="user",
                target_id=identity,
            )
            raise DomainError(
                str(exc),
                code="invalid_second_factor",
                status_code=status.HTTP_401_UNAUTHORIZED,
            ) from exc

        reset_login_attempts(TOTP_POLICY, identity)
        audit.record(
            AuditLog.Action.TWO_FACTOR_SUCCESS,
            request=request,
            actor_email=output_dto.email,
            target_type="user",
            target_id=output_dto.user_id,
        )
        audit.record(
            AuditLog.Action.LOGIN_SUCCESS,
            request=request,
            actor_email=output_dto.email,
            target_type="user",
            target_id=output_dto.user_id,
            second_factor=True,
        )

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


def _pre_auth_identity(pre_auth_token: str) -> str:
    """
    Extraer el identificador de cuenta de un pre_auth_token.

    Se usa solo como clave del contador de intentos, así que un token
    ilegible no es un error: se cae a una clave derivada del propio
    token, que sigue acotando la fuerza bruta de quien lo esté enviando.
    """
    try:
        return str(PreAuthToken(pre_auth_token).get("user_id") or "")
    except Exception:
        return f"unknown:{pre_auth_token[:32]}"


# ── Assets Views ───────────────────────────────────────────────────

class AssetListView(APIView):
    """
    GET /api/assets — Listar todos los activos criptográficos.
    Requiere autenticación JWT (Authorization: Bearer <token>).
    Caché Redis 60 s: los activos los actualiza Celery; no necesitamos recargar la BD en cada request.
    """
    permission_classes = [IsAuthenticated]
    _CACHE_KEY = "asset_list"
    _CACHE_TTL = 60  # 60 segundos

    @extend_schema(
        summary="Listar activos del catálogo",
        tags=["Mercado"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
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

    @extend_schema(
        summary="Serie de 7 días por símbolo",
        tags=["Mercado"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def get(self, request):
        from collections import defaultdict
        from datetime import timedelta

        from django.db.models import Avg
        from django.db.models.functions import TruncDate
        from django.utils import timezone

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


# ── Analysis Views ─────────────────────────────────────────────────

class RunAnalysisView(APIView):
    """
    POST /api/analysis/run — Solicitar ejecución de análisis técnico.
    Requiere autenticación JWT.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Registrar una ejecución de análisis",
        request=AnalysisRequestSerializer,
        tags=["Análisis"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request):
        serializer = AnalysisRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated = serializer.validated_data
        use_case = RunAnalysisUseCase()

        input_dto = AnalysisRequestInputDTO(
            asset_symbol=validated["asset_symbol"],
            analysis_type=validated["analysis_type"],
        )
        output_dto = use_case.execute(input_dto)

        out_serializer = AnalysisOutputSerializer(vars(output_dto))
        return Response(out_serializer.data, status=status.HTTP_202_ACCEPTED)


# ── Market Intelligence Views ─────────────────────────────────────

class MarketOverviewView(APIView):
    """
    GET /api/market/overview/ — Resumen global del mercado.
    Público: usado también desde la landing page (sin autenticación).
    Caché Redis 5 min: evita llamadas externas a CoinGecko/Alternative.me en cada request.
    """

    permission_classes = [AllowAny]
    _CACHE_KEY = "market_overview"
    _CACHE_TTL = 300  # 5 minutos

    @extend_schema(
        summary="Resumen global del mercado",
        tags=["Mercado"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def get(self, request):
        cached = cache.get(self._CACHE_KEY)
        if cached is not None:
            return Response(cached, status=status.HTTP_200_OK)

        output_dto = GetMarketOverviewUseCase().execute()
        serializer = MarketOverviewSerializer(vars(output_dto))
        data = serializer.data
        cache.set(self._CACHE_KEY, data, self._CACHE_TTL)
        return Response(data, status=status.HTTP_200_OK)

class FxRatesView(APIView):
    """
    GET /api/market/fx/ — Tasas de conversión USD→EUR/GBP.

    Público (datos no sensibles) y cacheado 1 hora: el frontend las usa
    para mostrar precios en la moneda preferida del usuario.
    """
    permission_classes = [AllowAny]
    _CACHE_KEY = "fx_rates"
    _CACHE_TTL = 3600  # 1 hora

    @extend_schema(
        summary="Tasas de conversión USD→EUR/GBP",
        tags=["Mercado"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
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

    @extend_schema(
        summary="Velas OHLCV de un activo",
        tags=["Mercado"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def get(self, request, symbol: str):
        from core.application.use_cases.get_asset_ohlcv import OhlcvNotAvailableError

        query_serializer = OhlcvQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

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
    GET /api/blockchain/metrics/ — Métricas on-chain filtrables.
    Requiere autenticación JWT.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Serie histórica de una métrica on-chain",
        tags=["On-chain"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def get(self, request):
        query_serializer = OnChainQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

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

    @extend_schema(
        summary="Estadísticas on-chain actuales",
        tags=["On-chain"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def get(self, request):
        symbol = request.query_params.get("symbol", "ETH").upper()
        result = GetMultiChainStatsUseCase().execute(symbol=symbol)
        return Response(result, status=status.HTTP_200_OK)

class NewsFeedView(APIView):
    """
    GET /api/news/ — Feed de noticias con filtro de sentimiento.
    Requiere autenticación JWT.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Feed de noticias con filtro de sentimiento",
        tags=["Noticias"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def get(self, request):
        query_serializer = NewsQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)

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


# ── Mock data ──────────────────────────────────────────────────────

def _get_mock_assets() -> list:
    """Datos de ejemplo para desarrollo cuando la BD está vacía."""
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
    """
    DELETE /api/auth/delete-account/ — Eliminar la cuenta permanentemente.

    Exige la contraseña actual: es una acción irreversible y no debe
    poder ejecutarla quien solo haya conseguido una sesión.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Eliminar la cuenta permanentemente",
        request=DeleteAccountSerializer,
        responses={
            204: OpenApiResponse(description="Cuenta eliminada."),
            400: OpenApiResponse(description="Contraseña incorrecta."),
        },
        tags=["Cuenta"],
    )
    def delete(self, request):
        serializer = DeleteAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = authenticate(
            request,
            username=request.user.email,
            password=serializer.validated_data["password"],
        )
        if user is None:
            audit.record(
                AuditLog.Action.ACCOUNT_DELETED,
                request=request,
                actor=request.user,
                outcome=AuditLog.Outcome.FAILURE,
                reason="wrong_password",
            )
            raise DomainError("Contraseña incorrecta.", code="invalid_password")

        # La traza se escribe ANTES del borrado: después, el usuario ya no
        # existe y `actor` quedaría a null. El email queda conservado en
        # `actor_email`, que es justo para lo que se denormalizó.
        deleted_email = request.user.email
        deleted_id = request.user.pk

        repo = DjangoUserRepository()
        result = DeleteUserAccountUseCase(repo).execute(deleted_id)

        if not result.get("success"):
            raise DomainError(
                result.get("error") or "No se ha podido eliminar la cuenta.",
                code="account_deletion_failed",
            )

        audit.record(
            AuditLog.Action.ACCOUNT_DELETED,
            request=request,
            actor_email=deleted_email,
            target_type="user",
            target_id=deleted_id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Analysis avanzado Views ────────────────────────────────────────


class CalculateAnalysisView(APIView):
    """
    POST /api/analysis/calculate/ — Calcula un indicador técnico con datos reales.
    Reemplaza al antiguo RunAnalysisView con cálculos reales.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Calcular un indicador técnico",
        request=CalculateAnalysisSerializer,
        tags=["Análisis"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request):
        serializer = CalculateAnalysisSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

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

    @extend_schema(
        summary="Panel multi-indicador con veredicto",
        request=SignalsRequestSerializer,
        tags=["Análisis"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request):
        serializer = SignalsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        v = serializer.validated_data
        result = GetSignalsDashboardUseCase().execute(
            SignalsRequestDTO(
                asset_symbol=v["asset_symbol"],
                interval=v.get("interval", "1h"),
            )
        )
        return Response(result, status=status.HTTP_200_OK)


class PredictPriceView(APIView):
    """
    POST /api/analysis/predict/ — Predicción ML de dirección de precio.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Predicción ML de dirección de precio",
        request=PredictionRequestSerializer,
        tags=["Análisis"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request):
        serializer = PredictionRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        v = serializer.validated_data
        result = PredictPriceUseCase().execute(
            PredictionRequestDTO(
                asset_symbol=v["asset_symbol"],
                interval=v.get("interval", "1h"),
                horizon=v.get("horizon", 5),
            )
        )
        return Response(result, status=status.HTTP_200_OK)


class DetectPatternsView(APIView):
    """
    POST /api/analysis/patterns/ — Detección de patrones de velas.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Detectar patrones de velas",
        request=PatternsRequestSerializer,
        tags=["Análisis"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request):
        serializer = PatternsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

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

    @extend_schema(
        summary="Backtesting de una estrategia",
        request=BacktestRequestSerializer,
        tags=["Análisis"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request):
        serializer = BacktestRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        v = serializer.validated_data
        result = RunBacktestUseCase().execute(
            BacktestRequestDTO(
                asset_symbol=v["asset_symbol"],
                strategy=v["strategy"],
                interval=v.get("interval", "1h"),
                limit=v.get("limit", 500),
                initial_capital=v.get("initial_capital", 10000.0),
            )
        )
        return Response(result, status=status.HTTP_200_OK)


class AssetDetailInfoView(APIView):
    """
    GET /api/assets/<symbol>/info/ — Información de proyecto de un activo.

    Consolida desde CoinGecko: enlaces (web, whitepaper, twitter, reddit),
    datos de mercado (ATH, suministro) y categorías.
    Requiere autenticación JWT.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Ficha de proyecto de un activo",
        tags=["Mercado"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
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

    @extend_schema(
        summary="Estrategias disponibles para backtesting",
        tags=["Análisis"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def get(self, request):
        strategies = RunBacktestUseCase.get_available_strategies()
        return Response(strategies, status=status.HTTP_200_OK)


# ── Portfolio Views ────────────────────────────────────────────────

class PortfolioView(APIView):
    """
    GET  /api/portfolio/  — Resumen del portfolio con PnL calculado.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Resumen del portfolio con PnL",
        tags=["Portfolio"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
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

    @extend_schema(
        summary="Historial de operaciones",
        tags=["Portfolio"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def get(self, request):
        query_ser = TradeHistoryQuerySerializer(data=request.query_params)
        query_ser.is_valid(raise_exception=True)
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

    @extend_schema(
        summary="Registrar una operación",
        request=AddTradeSerializer,
        tags=["Portfolio"],
        responses={201: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request):
        serializer = AddTradeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        v = serializer.validated_data
        trade = AddTradeUseCase().execute(
            user=request.user,
            dto=AddTradeInputDTO(
                asset_symbol=v["asset_symbol"],
                trade_type=v["trade_type"],
                quantity=v["quantity"],
                price_usd=v["price_usd"],
                executed_at=v["executed_at"].isoformat(),
                notes=v.get("notes", ""),
            ),
        )

        return Response(
            TradeOutputSerializer(vars(trade)).data,
            status=status.HTTP_201_CREATED,
        )


class TradeDetailView(APIView):
    """
    DELETE /api/portfolio/trades/<trade_id>/  — Eliminar una operación.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Eliminar una operación",
        tags=["Portfolio"],
        responses={204: OpenApiResponse(description="Recurso eliminado.")},
    )
    def delete(self, request, trade_id: int):
        try:
            DeleteTradeUseCase().execute(user=request.user, trade_id=trade_id)
        except ValueError as exc:
            raise DomainError(
                str(exc), code="not_found", status_code=status.HTTP_404_NOT_FOUND
            ) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Alerts Views ───────────────────────────────────────────────────

class AlertListView(APIView):
    """
    GET  /api/alerts/  — Listar todas las alertas del usuario.
    POST /api/alerts/  — Crear nueva alerta de precio.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Listar alertas de precio",
        tags=["Alertas"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def get(self, request):
        active_only = request.query_params.get("active_only", "false").lower() == "true"
        alerts = ListAlertsUseCase().execute(request.user, active_only=active_only)
        return Response(
            AlertOutputSerializer([vars(a) for a in alerts], many=True).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Crear una alerta de precio",
        request=CreateAlertSerializer,
        tags=["Alertas"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request):
        serializer = CreateAlertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        v = serializer.validated_data
        alert = CreateAlertUseCase().execute(
            user=request.user,
            dto=CreateAlertInputDTO(
                asset_symbol=v["asset_symbol"],
                condition=v["condition"],
                threshold_price=v["threshold_price"],
                notes=v.get("notes", ""),
            ),
        )

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

    @extend_schema(
        summary="Eliminar una alerta",
        tags=["Alertas"],
        responses={204: OpenApiResponse(description="Recurso eliminado.")},
    )
    def delete(self, request, alert_id: int):
        try:
            DeleteAlertUseCase().execute(user=request.user, alert_id=alert_id)
        except ValueError as exc:
            raise DomainError(
                str(exc), code="not_found", status_code=status.HTTP_404_NOT_FOUND
            ) from exc
        return Response(status=status.HTTP_204_NO_CONTENT)


class AlertToggleView(APIView):
    """
    PATCH /api/alerts/<alert_id>/toggle/ — Activar/desactivar una alerta.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Activar o desactivar una alerta",
        request=None,
        tags=["Alertas"],
        responses={200: OpenApiResponse(description="Alerta con su nuevo estado.")},
    )
    def patch(self, request, alert_id: int):
        try:
            alert = ToggleAlertUseCase().execute(user=request.user, alert_id=alert_id)
        except ValueError as exc:
            raise DomainError(
                str(exc), code="not_found", status_code=status.HTTP_404_NOT_FOUND
            ) from exc
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

    @extend_schema(
        summary="Listar posiciones",
        tags=["Portfolio"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def get(self, request):
        query_ser = PositionsQuerySerializer(data=request.query_params)
        query_ser.is_valid(raise_exception=True)

        status_filter = query_ser.validated_data.get("status") or None
        summary = GetPositionsUseCase().execute(user=request.user, status=status_filter)

        return Response(
            PositionSummaryOutputSerializer(vars(summary)).data,
            status=status.HTTP_200_OK,
        )

    @extend_schema(
        summary="Abrir una posición",
        request=OpenPositionSerializer,
        tags=["Portfolio"],
        responses={201: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request):
        serializer = OpenPositionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        v = serializer.validated_data
        position = OpenPositionUseCase().execute(
            user=request.user,
            dto=OpenPositionInputDTO(
                asset_symbol=v["asset_symbol"],
                direction=v["direction"],
                quantity=v["quantity"],
                entry_price=v["entry_price"],
                opened_at=v["opened_at"].isoformat(),
                label=v.get("label", ""),
                notes=v.get("notes", ""),
            ),
        )

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

    @extend_schema(
        summary="Renombrar una posición",
        request=UpdatePositionSerializer,
        tags=["Portfolio"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def patch(self, request, position_id: int):
        serializer = UpdatePositionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            pos = PositionModel.objects.get(pk=position_id, user=request.user)
        except PositionModel.DoesNotExist:
            raise DomainError(
                "Posición no encontrada.", code="not_found",
                status_code=status.HTTP_404_NOT_FOUND,
            ) from None

        pos.label = serializer.validated_data["label"]
        pos.save(update_fields=["label", "updated_at"])

        from decimal import Decimal

        from core.application.use_cases.open_position import _build_position_dto
        current_price = Decimal(str(pos.asset.current_price or pos.avg_entry_price))
        dto = _build_position_dto(pos, current_price)
        return Response(PositionOutputSerializer(vars(dto)).data, status=status.HTTP_200_OK)

    @extend_schema(
        summary="Eliminar una posición sin trades",
        tags=["Portfolio"],
        responses={204: OpenApiResponse(description="Recurso eliminado.")},
    )
    def delete(self, request, position_id: int):
        try:
            pos = PositionModel.objects.get(pk=position_id, user=request.user)
        except PositionModel.DoesNotExist:
            raise DomainError(
                "Posición no encontrada.", code="not_found",
                status_code=status.HTTP_404_NOT_FOUND,
            ) from None

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

    @extend_schema(
        summary="Ampliar una posición (AVCO)",
        request=AddToPositionSerializer,
        tags=["Portfolio"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request, position_id: int):
        serializer = AddToPositionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        v = serializer.validated_data
        position = ScalePositionUseCase().execute(
            user=request.user,
            position_id=position_id,
            dto=AddToPositionInputDTO(
                quantity=v["quantity"],
                entry_price=v["entry_price"],
                executed_at=v["executed_at"].isoformat(),
                notes=v.get("notes", ""),
            ),
        )

        return Response(
            PositionOutputSerializer(vars(position)).data,
            status=status.HTTP_200_OK,
        )


class PositionCloseView(APIView):
    """
    POST /api/portfolio/positions/<position_id>/close/ — Cerrar posición parcial o totalmente.
    """
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="Cerrar una posición total o parcialmente",
        request=ClosePositionSerializer,
        tags=["Portfolio"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request, position_id: int):
        serializer = ClosePositionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        v = serializer.validated_data
        position = ClosePositionUseCase().execute(
            user=request.user,
            position_id=position_id,
            dto=ClosePositionInputDTO(
                close_quantity=v["close_quantity"],
                close_price=v["close_price"],
                executed_at=v["executed_at"].isoformat(),
                notes=v.get("notes", ""),
            ),
        )

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

    @extend_schema(
        summary="Listar la watchlist del usuario",
        tags=["Watchlist"],
        responses={200: OpenApiResponse(description="Operación completada.")},
    )
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

    @extend_schema(
        summary="Añadir un activo a la watchlist",
        request=WatchlistAddSerializer,
        tags=["Watchlist"],
        responses={201: OpenApiResponse(description="Operación completada.")},
    )
    def post(self, request):
        serializer = WatchlistAddSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        symbol = serializer.validated_data["symbol"].upper()
        try:
            asset = CryptoAssetModel.objects.get(symbol=symbol)
        except CryptoAssetModel.DoesNotExist:
            raise DomainError(
                f"Activo '{symbol}' no encontrado.", code="not_found",
                status_code=status.HTTP_404_NOT_FOUND,
            ) from None

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

    @extend_schema(
        summary="Quitar un activo de la watchlist",
        tags=["Watchlist"],
        responses={204: OpenApiResponse(description="Recurso eliminado.")},
    )
    def delete(self, request, symbol: str):
        deleted, _ = UserWatchlistModel.objects.filter(
            user=request.user,
            asset__symbol=symbol.upper(),
        ).delete()
        if not deleted:
            raise DomainError(
                "El activo no está en la watchlist.", code="not_found",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)
