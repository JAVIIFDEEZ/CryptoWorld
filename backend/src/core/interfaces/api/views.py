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

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate

from core.interfaces.api.serializers import (
    RegisterSerializer,
    LoginSerializer,
    CryptoAssetSerializer,
    AnalysisRequestSerializer,
    AnalysisOutputSerializer,
)
from core.application.use_cases.register_user import RegisterUserUseCase
from core.application.use_cases.get_assets import GetAssetsUseCase
from core.application.use_cases.run_analysis import RunAnalysisUseCase
from core.application.dto.auth_dto import RegisterUserInputDTO, LoginInputDTO
from core.application.dto.asset_dto import AnalysisRequestInputDTO
from core.infrastructure.persistence.repositories_impl import (
    DjangoUserRepository,
    DjangoCryptoAssetRepository,
)
from core.domain.services.user_domain_service import UserDomainService


# ── Health Check ───────────────────────────────────────────────────

class HealthCheckView(APIView):
    """
    GET /api/health — Endpoint de comprobación de estado del servidor.
    No requiere autenticación. Útil para monitorización y Docker healthcheck.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(
            {"status": "ok", "version": "1.0.0", "service": "CryptoWorld API"},
            status=status.HTTP_200_OK,
        )


# ── Auth Views ─────────────────────────────────────────────────────

class RegisterView(APIView):
    """
    POST /api/auth/register — Registrar un nuevo usuario.

    Flujo:
      1. Validar datos de entrada con RegisterSerializer
      2. Construir DTO de entrada
      3. Delegar al caso de uso RegisterUserUseCase
      4. Devolver respuesta 201 con datos del usuario creado
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated = serializer.validated_data

        # Construir las dependencias y el caso de uso
        # En un proyecto más grande esto se haría con un contenedor DI (dependency-injector)
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

            # El modelo Django maneja el hash; actualizamos contraseña a mano
            from core.infrastructure.persistence.models import User as UserModel
            user_model = UserModel.objects.get(pk=output_dto.id)
            user_model.set_password(validated["password"])
            user_model.save()

        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                "id": output_dto.id,
                "email": output_dto.email,
                "username": output_dto.username,
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(APIView):
    """
    POST /api/auth/login — Autenticar usuario y devolver tokens JWT.

    Flujo:
      1. Validar credenciales con LoginSerializer
      2. Autenticar con Django auth (verifica contraseña hasheada)
      3. Generar par de tokens JWT con SimpleJWT
      4. Devolver access_token y refresh_token
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        validated = serializer.validated_data

        # Django authenticate busca por USERNAME_FIELD (email en nuestro caso)
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

        # Generar tokens JWT
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                "access_token": str(refresh.access_token),
                "refresh_token": str(refresh),
                "user_id": user.pk,
                "email": user.email,
                "username": user.username,
            },
            status=status.HTTP_200_OK,
        )


# ── Assets Views ───────────────────────────────────────────────────

class AssetListView(APIView):
    """
    GET /api/assets — Listar todos los activos criptográficos.

    Requiere autenticación JWT (Authorization: Bearer <token>).
    Si la BD está vacía, devuelve mock data para desarrollo.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        asset_repo = DjangoCryptoAssetRepository()
        use_case = GetAssetsUseCase(asset_repo)
        output_dtos = use_case.execute()

        # Si no hay activos en BD, devolver mock para desarrollo
        if not output_dtos:
            mock_assets = _get_mock_assets()
            return Response(mock_assets, status=status.HTTP_200_OK)

        serializer = CryptoAssetSerializer(
            [vars(dto) for dto in output_dtos],
            many=True,
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


# ── Analysis Views ─────────────────────────────────────────────────

class RunAnalysisView(APIView):
    """
    POST /api/analysis/run — Solicitar ejecución de análisis técnico.

    Estructura base lista para ampliar con análisis cuantitativos reales.
    Requiere autenticación JWT.
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


# ── Mock data ──────────────────────────────────────────────────────

def _get_mock_assets() -> list:
    """
    Datos de ejemplo para desarrollo cuando la BD está vacía.
    Se sustituirán por datos reales de CoinGecko en fases siguientes.
    """
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
