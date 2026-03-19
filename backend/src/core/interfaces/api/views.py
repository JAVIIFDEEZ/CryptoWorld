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
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate

from core.interfaces.api.serializers import (
    RegisterSerializer,
    LoginSerializer,
    LogoutSerializer,
    VerifyEmailSerializer,
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
)
from core.application.use_cases.register_user import RegisterUserUseCase
from core.application.use_cases.get_assets import GetAssetsUseCase
from core.application.use_cases.run_analysis import RunAnalysisUseCase
from core.application.use_cases.logout import LogoutUseCase
from core.application.use_cases.verify_email import VerifyEmailUseCase
from core.application.use_cases.send_verification_email import SendVerificationEmailUseCase
from core.application.use_cases.request_password_reset import RequestPasswordResetUseCase
from core.application.use_cases.confirm_password_reset import ConfirmPasswordResetUseCase
from core.application.use_cases.change_password import ChangePasswordUseCase
from core.application.use_cases.setup_2fa import Setup2FAUseCase
from core.application.use_cases.enable_2fa import Enable2FAUseCase
from core.application.use_cases.disable_2fa import Disable2FAUseCase
from core.application.use_cases.verify_2fa_login import Verify2FALoginUseCase, PreAuthToken
from core.application.use_cases.get_market_overview import GetMarketOverviewUseCase
from core.application.use_cases.get_asset_ohlcv import GetAssetOhlcvUseCase
from core.application.use_cases.get_onchain_metrics import GetOnChainMetricsUseCase
from core.application.use_cases.get_news_feed import GetNewsFeedUseCase
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
from core.application.dto.asset_dto import AnalysisRequestInputDTO
from core.infrastructure.persistence.repositories_impl import (
    DjangoUserRepository,
    DjangoCryptoAssetRepository,
)
from core.domain.services.user_domain_service import UserDomainService


# â”€â”€ Health Check â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class HealthCheckView(APIView):
    """
    GET /api/health â€” Endpoint de comprobaciÃ³n de estado del servidor.
    No requiere autenticaciÃ³n. Ãštil para monitorizaciÃ³n y Docker healthcheck.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {"status": "ok", "version": "1.0.0", "service": "CryptoWorld API"},
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

            from core.infrastructure.persistence.models import User as UserModel
            user_model = UserModel.objects.get(pk=output_dto.id)
            user_model.set_password(validated["password"])
            user_model.save()

            # Enviar email de verificaciÃ³n (se imprime en consola en desarrollo)
            SendVerificationEmailUseCase().execute(output_dto.id)

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
                {"error": "Credenciales invÃ¡lidas."},
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
                    "error": "Debes verificar tu email antes de iniciar sesiÃ³n.",
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

        return Response({"message": "SesiÃ³n cerrada correctamente."}, status=status.HTTP_200_OK)


class MeView(APIView):
    """
    GET /api/auth/me/ â€” Devolver los datos del usuario autenticado.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response(
            {
                "id": user.pk,
                "email": user.email,
                "username": user.username,
                "is_active": user.is_active,
                "is_email_verified": user.is_email_verified,
                "is_2fa_enabled": user.is_2fa_enabled,
                "date_joined": user.date_joined.isoformat(),
            },
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

    def post(self, request):
        serializer = ResendVerificationRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Respuesta indistinguible para evitar enumeraciÃ³n de emails.
        from core.infrastructure.persistence.models import User as UserModel
        user = UserModel.objects.filter(email=serializer.validated_data["email"]).first()
        if user and not user.is_email_verified:
            SendVerificationEmailUseCase().execute(user.pk)

        return Response(
            {"message": "Si el email existe y no estÃ¡ verificado, recibirÃ¡s un enlace."},
            status=status.HTTP_200_OK,
        )


class PasswordResetRequestView(APIView):
    """
    POST /api/auth/password-reset/ â€” Solicitar link de recuperaciÃ³n por email.
    No requiere autenticaciÃ³n. No revela si el email existe.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PasswordResetRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        RequestPasswordResetUseCase().execute(
            PasswordResetRequestDTO(email=serializer.validated_data["email"])
        )

        # Respuesta siempre igual para no revelar si el email existe
        return Response(
            {"message": "Si el email existe, recibirÃ¡s un enlace de recuperaciÃ³n."},
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
            {"message": "ContraseÃ±a restablecida correctamente."},
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
            {"message": "ContraseÃ±a cambiada correctamente."},
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
            Enable2FAUseCase().execute(
                Enable2FADTO(
                    user_id=request.user.pk,
                    totp_code=serializer.validated_data["totp_code"],
                )
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {"message": "2FA activado correctamente."},
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


class Verify2FALoginView(APIView):
    """
    POST /api/auth/2fa/login/ â€” Segunda fase del login con 2FA.

    Recibe el pre_auth_token (obtenido del login normal) y el cÃ³digo TOTP.
    Si ambos son vÃ¡lidos, devuelve los tokens JWT completos.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = Verify2FALoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        v = serializer.validated_data
        try:
            output_dto = Verify2FALoginUseCase().execute(
                Verify2FALoginDTO(
                    pre_auth_token=v["pre_auth_token"],
                    totp_code=v["totp_code"],
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
            },
            status=status.HTTP_200_OK,
        )


# â”€â”€ Assets Views â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

class AssetListView(APIView):
    """
    GET /api/assets â€” Listar todos los activos criptogrÃ¡ficos.
    Requiere autenticaciÃ³n JWT (Authorization: Bearer <token>).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
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
        return Response(serializer.data, status=status.HTTP_200_OK)


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
    GET /api/market/overview/ â€” Resumen global del mercado.
    Requiere autenticaciÃ³n JWT.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        output_dto = GetMarketOverviewUseCase().execute()
        serializer = MarketOverviewSerializer(vars(output_dto))
        return Response(serializer.data, status=status.HTTP_200_OK)


class AssetOhlcvView(APIView):
    """
    GET /api/assets/<symbol>/ohlcv/ â€” Serie de velas para grÃ¡ficos interactivos.
    Requiere autenticaciÃ³n JWT.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request, symbol: str):
        query_serializer = OhlcvQuerySerializer(data=request.query_params)
        if not query_serializer.is_valid():
            return Response(query_serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        q = query_serializer.validated_data
        candles = GetAssetOhlcvUseCase().execute(
            symbol=symbol,
            interval=q["interval"],
            limit=q["limit"],
        )
        serializer = OhlcvCandleSerializer([vars(c) for c in candles], many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


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
        points = GetOnChainMetricsUseCase().execute(
            symbol=q["symbol"],
            metric=q["metric"],
            days=q["days"],
        )
        serializer = OnChainMetricPointSerializer([vars(p) for p in points], many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


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
        items = GetNewsFeedUseCase().execute(
            query=q["q"],
            sentiment=q["sentiment"],
            limit=q["limit"],
        )
        serializer = NewsItemSerializer([vars(i) for i in items], many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


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


from core.application.use_cases.delete_user_account import DeleteUserAccountUseCase
from core.interfaces.api.serializers import DeleteAccountSerializer

class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        serializer = DeleteAccountSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = authenticate(email=request.user.email, password=serializer.validated_data['password'])
        if user is None:
            return Response({'error': 'Contrasena incorrecta'}, status=status.HTTP_400_BAD_REQUEST)

        from core.infrastructure.persistence.repositories_impl import DjangoUserRepository
        repo = DjangoUserRepository()
        use_case = DeleteUserAccountUseCase(repo)
        result = use_case.execute(request.user.id)

        if result.get('success'):
            return Response(status=status.HTTP_204_NO_CONTENT)
        return Response({'error': result.get('error')}, status=status.HTTP_400_BAD_REQUEST)



