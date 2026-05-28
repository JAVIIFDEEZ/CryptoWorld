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
    DeleteAccountSerializer,
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

            # El repositorio crea el usuario sin contraseña;
            # la establecemos aquí usando el método del repositorio.
            user_repo.set_password(output_dto.id, validated["password"])

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
                "is_admin": user.is_staff or user.is_superuser,
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
            {"message": "Si el email existe y no está verificado, recibirás un enlace."},
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
                "is_admin": output_dto.is_admin,
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



class AssetSparklinesView(APIView):
    """
    GET /api/assets/sparklines/?symbols=BTC,ETH,SOL

    Devuelve precios de cierre diarios (ultimos 7 dias) por simbolo,
    listos para renderizar mini-sparklines en tablas y tarjetas.

    Respuesta: { "BTC": [p1, p2, ...], "ETH": [...], ... }
    Maximo 10 simbolos por peticion para no exceder el rate-limit de CoinGecko.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from core.infrastructure.external_apis.coingecko_client import (
            CoinGeckoClient,
            CoinGeckoClientError,
        )

        raw = request.query_params.get("symbols", "")
        if not raw:
            return Response(
                {"error": "Parametro symbols requerido."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        symbols = [s.strip().upper() for s in raw.split(",") if s.strip()][:10]

        assets = (
            CryptoAssetModel.objects
            .filter(symbol__in=symbols)
            .values("symbol", "coingecko_id")
        )
        id_map = {a["symbol"]: a["coingecko_id"] for a in assets if a["coingecko_id"]}

        client = CoinGeckoClient()
        result = {}

        for symbol in symbols:
            coingecko_id = id_map.get(symbol)
            if not coingecko_id:
                result[symbol] = []
                continue
            try:
                result[symbol] = client.get_sparkline_prices(coingecko_id, days=7)
            except CoinGeckoClientError:
                result[symbol] = []

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
    """

    permission_classes = [AllowAny]

    def get(self, request):
        output_dto = GetMarketOverviewUseCase().execute()
        serializer = MarketOverviewSerializer(vars(output_dto))
        return Response(serializer.data, status=status.HTTP_200_OK)

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
            )
        )
        return Response(result, status=status.HTTP_200_OK)


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
