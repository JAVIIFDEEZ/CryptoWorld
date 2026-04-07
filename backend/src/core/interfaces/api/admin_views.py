"""
interfaces/api/admin_views.py — Controladores HTTP para el panel de administración.

Todos los endpoints requieren autenticación + rol de admin (IsAdmin permission).
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from core.interfaces.api.permissions import IsAdmin
from core.interfaces.api.admin_serializers import (
    AdminUserSerializer,
    AdminUpdateUserSerializer,
    AdminAssetSerializer,
    AdminCreateAssetSerializer,
    AdminUpdateAssetSerializer,
    AdminStatsSerializer,
)
from core.application.use_cases.admin_list_users import AdminListUsersUseCase
from core.application.use_cases.admin_update_user import AdminUpdateUserUseCase
from core.application.use_cases.admin_delete_user import AdminDeleteUserUseCase
from core.application.use_cases.admin_manage_asset import (
    AdminListAssetsUseCase,
    AdminCreateAssetUseCase,
    AdminUpdateAssetUseCase,
    AdminDeleteAssetUseCase,
)
from core.application.use_cases.admin_get_stats import AdminGetStatsUseCase
from core.application.dto.admin_dto import (
    AdminUpdateUserInputDTO,
    AdminCreateAssetInputDTO,
    AdminUpdateAssetInputDTO,
)
from core.infrastructure.persistence.repositories_impl import (
    DjangoUserRepository,
    DjangoCryptoAssetRepository,
)


# ── Stats ──────────────────────────────────────────────────────────

class AdminStatsView(APIView):
    """
    GET /api/admin/stats/ — Estadísticas globales del sistema.
    """
    permission_classes = [IsAdmin]

    def get(self, request):
        output_dto = AdminGetStatsUseCase().execute()
        serializer = AdminStatsSerializer(vars(output_dto))
        return Response(serializer.data, status=status.HTTP_200_OK)


# ── Users ──────────────────────────────────────────────────────────

class AdminUserListView(APIView):
    """
    GET /api/admin/users/ — Listar todos los usuarios.
    """
    permission_classes = [IsAdmin]

    def get(self, request):
        user_repo = DjangoUserRepository()
        use_case = AdminListUsersUseCase(user_repo)
        output_dtos = use_case.execute()
        serializer = AdminUserSerializer(
            [vars(dto) for dto in output_dtos],
            many=True,
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class AdminUserDetailView(APIView):
    """
    GET    /api/admin/users/<id>/ — Detalle de un usuario.
    PATCH  /api/admin/users/<id>/ — Editar usuario.
    DELETE /api/admin/users/<id>/ — Eliminar usuario.
    """
    permission_classes = [IsAdmin]

    def get(self, request, user_id: int):
        user_repo = DjangoUserRepository()
        user_entity = user_repo.get_by_id(user_id)
        if user_entity is None:
            return Response(
                {"error": "Usuario no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        from core.application.dto.admin_dto import AdminUserOutputDTO
        output_dto = AdminUserOutputDTO(
            id=user_entity.id,
            email=user_entity.email,
            username=user_entity.username,
            is_active=user_entity.is_active,
            is_staff=user_entity.is_staff,
            role=user_entity.role,
            is_email_verified=user_entity.is_email_verified,
            is_2fa_enabled=user_entity.is_2fa_enabled,
            date_joined=user_entity.date_joined.isoformat() if hasattr(user_entity.date_joined, 'isoformat') else str(user_entity.date_joined),
        )
        serializer = AdminUserSerializer(vars(output_dto))
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request, user_id: int):
        serializer = AdminUpdateUserSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user_repo = DjangoUserRepository()
        use_case = AdminUpdateUserUseCase(user_repo)

        try:
            input_dto = AdminUpdateUserInputDTO(
                user_id=user_id,
                **serializer.validated_data,
            )
            output_dto = use_case.execute(input_dto)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        out_serializer = AdminUserSerializer(vars(output_dto))
        return Response(out_serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, user_id: int):
        user_repo = DjangoUserRepository()
        use_case = AdminDeleteUserUseCase(user_repo)

        try:
            use_case.execute(user_id=user_id, admin_user_id=request.user.pk)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Assets ─────────────────────────────────────────────────────────

class AdminAssetListView(APIView):
    """
    GET  /api/admin/assets/ — Listar todos los activos.
    POST /api/admin/assets/ — Crear un activo manualmente.
    """
    permission_classes = [IsAdmin]

    def get(self, request):
        asset_repo = DjangoCryptoAssetRepository()
        use_case = AdminListAssetsUseCase(asset_repo)
        output_dtos = use_case.execute()
        serializer = AdminAssetSerializer(
            [vars(dto) for dto in output_dtos],
            many=True,
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = AdminCreateAssetSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        asset_repo = DjangoCryptoAssetRepository()
        use_case = AdminCreateAssetUseCase(asset_repo)

        try:
            v = serializer.validated_data
            input_dto = AdminCreateAssetInputDTO(
                symbol=v["symbol"],
                name=v["name"],
                current_price=v["current_price"],
                market_cap=v.get("market_cap") or None,
                volume_24h=v.get("volume_24h") or None,
                price_change_24h=v.get("price_change_24h") or None,
                coingecko_id=v.get("coingecko_id") or None,
                logo_url=v.get("logo_url") or None,
            )
            output_dto = use_case.execute(input_dto)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        out_serializer = AdminAssetSerializer(vars(output_dto))
        return Response(out_serializer.data, status=status.HTTP_201_CREATED)


class AdminAssetDetailView(APIView):
    """
    PATCH  /api/admin/assets/<id>/ — Editar un activo.
    DELETE /api/admin/assets/<id>/ — Eliminar un activo.
    """
    permission_classes = [IsAdmin]

    def patch(self, request, asset_id: int):
        serializer = AdminUpdateAssetSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        asset_repo = DjangoCryptoAssetRepository()
        use_case = AdminUpdateAssetUseCase(asset_repo)

        try:
            input_dto = AdminUpdateAssetInputDTO(
                asset_id=asset_id,
                **serializer.validated_data,
            )
            output_dto = use_case.execute(input_dto)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        out_serializer = AdminAssetSerializer(vars(output_dto))
        return Response(out_serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, asset_id: int):
        asset_repo = DjangoCryptoAssetRepository()
        use_case = AdminDeleteAssetUseCase(asset_repo)

        try:
            use_case.execute(asset_id=asset_id)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(status=status.HTTP_204_NO_CONTENT)
