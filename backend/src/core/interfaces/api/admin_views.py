"""
interfaces/api/admin_views.py — Endpoints de administración.

Modelo de privilegios en dos niveles, que antes no existía:

  - **Staff** (`is_staff`): opera el panel. Consulta usuarios, fuerza
    verificaciones de email, bloquea y desbloquea cuentas, lanza la
    sincronización del catálogo de mercado.
  - **Superusuario** (`is_superuser`): además, concede y revoca
    privilegios y da de alta nuevos administradores.

La distinción importa: antes cualquier cuenta con `is_staff` podía crear
superusuarios, de modo que el nivel más bajo de administración concedía
de hecho el más alto. Ahora la elevación de privilegios está reservada a
quien ya los tiene y queda registrada en el log de auditoría.

Reglas de negocio conservadas:
  - Nadie puede bloquearse ni degradarse a sí mismo (evita dejar la
    plataforma sin administradores por accidente).
  - No se puede revocar el último superusuario activo del sistema.
  - Las contraseñas de nuevos administradores pasan los validadores de
    Django (longitud, comunes, numéricas…).
"""

import logging

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAdminUser, BasePermission
from rest_framework.response import Response
from rest_framework.views import APIView

from core.application.services import audit
from core.application.services.sessions import revoke_all_sessions
from core.application.use_cases.sync_market_data import SyncMarketDataUseCase
from core.infrastructure.persistence.models import AuditLog, User
from core.interfaces.api.exception_handler import DomainError
from core.interfaces.api.pagination import paginate_list
from core.tasks import dispatch_task
from core.tasks import send_verification_email as send_verification_email_task

logger = logging.getLogger(__name__)


class IsSuperUser(BasePermission):
    """Solo superusuarios: conceder o revocar privilegios y crear administradores."""

    message = "Esta acción requiere privilegios de superusuario."

    def has_permission(self, request, view) -> bool:
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_superuser
        )


# ── Serializers ────────────────────────────────────────────────────


class AdminUserOutputSerializer(serializers.Serializer):
    """Vista pública de un usuario en el panel de administración."""

    id = serializers.IntegerField()
    email = serializers.EmailField()
    username = serializers.CharField()
    is_active = serializers.BooleanField()
    is_email_verified = serializers.BooleanField()
    is_2fa_enabled = serializers.BooleanField()
    is_staff = serializers.BooleanField()
    is_superuser = serializers.BooleanField()
    is_admin = serializers.BooleanField()
    date_joined = serializers.CharField()
    last_login = serializers.CharField(allow_null=True)


class CreateAdminSerializer(serializers.Serializer):
    """Valida POST /api/admin/users/ — alta de un administrador."""

    email = serializers.EmailField()
    username = serializers.CharField(min_length=3, max_length=150)
    password = serializers.CharField(write_only=True)
    # Por defecto se crea staff, NO superusuario: el privilegio máximo
    # debe pedirse explícitamente (principio de mínimo privilegio).
    is_superuser = serializers.BooleanField(required=False, default=False)

    def validate_email(self, value: str) -> str:
        return value.strip().lower()

    def validate_username(self, value: str) -> str:
        return value.strip()


class UpdateUserSerializer(serializers.Serializer):
    """Valida PATCH /api/admin/users/<id>/."""

    is_active = serializers.BooleanField(required=False)
    is_staff = serializers.BooleanField(required=False)
    is_superuser = serializers.BooleanField(required=False)
    is_email_verified = serializers.BooleanField(required=False)

    def validate(self, data: dict) -> dict:
        if not data:
            raise serializers.ValidationError(
                "Debes indicar al menos un campo a actualizar."
            )
        return data


class MarketSyncSerializer(serializers.Serializer):
    """Valida POST /api/admin/market/sync/."""

    per_page = serializers.IntegerField(
        min_value=1, max_value=250, default=100, required=False
    )


def _serialize_user(u: User) -> dict:
    return {
        "id": u.pk,
        "email": u.email,
        "username": u.username,
        "is_active": u.is_active,
        "is_email_verified": u.is_email_verified,
        "is_2fa_enabled": u.is_2fa_enabled,
        "is_staff": u.is_staff,
        "is_superuser": u.is_superuser,
        # Compatibilidad con el cliente actual, que espera `is_admin`.
        "is_admin": u.is_staff or u.is_superuser,
        "date_joined": u.date_joined.isoformat(),
        "last_login": u.last_login.isoformat() if u.last_login else None,
    }


# ── Views ──────────────────────────────────────────────────────────


class AdminUserListView(APIView):
    """
    GET  /api/admin/users/?search=&page=  — Listar usuarios (paginado).
    POST /api/admin/users/                — Crear un administrador (superusuario).
    """

    permission_classes = [IsAdminUser]

    def get_permissions(self):
        # El alta de administradores exige superusuario; el listado, no.
        if self.request.method == "POST":
            return [IsAdminUser(), IsSuperUser()]
        return super().get_permissions()

    @extend_schema(
        summary="Listar usuarios",
        parameters=[
            OpenApiParameter("search", str, description="Filtro por email o nombre de usuario."),
            OpenApiParameter("page", int, description="Página solicitada."),
            OpenApiParameter("page_size", int, description="Tamaño de página (máx. 200)."),
        ],
        responses={200: AdminUserOutputSerializer(many=True)},
        tags=["Administración"],
    )
    def get(self, request):
        users = User.objects.all().order_by("-date_joined")

        search = request.query_params.get("search", "").strip()
        if search:
            users = users.filter(
                Q(email__icontains=search) | Q(username__icontains=search)
            )

        # Paginado: sin esto la respuesta crecía con la tabla entera de
        # usuarios, lo que es a la vez un problema de memoria del proceso
        # web y un vector de denegación de servicio trivial.
        return paginate_list(
            request,
            users,
            lambda page: [_serialize_user(u) for u in page],
            view=self,
        )

    @extend_schema(
        summary="Crear un administrador",
        request=CreateAdminSerializer,
        responses={
            201: OpenApiResponse(description="Administrador creado."),
            403: OpenApiResponse(description="Requiere privilegios de superusuario."),
        },
        tags=["Administración"],
    )
    def post(self, request):
        serializer = CreateAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data

        email = v["email"]
        username = v["username"]

        if User.objects.filter(email__iexact=email).exists():
            raise DomainError("El email ya está en uso.", code="email_taken")

        if User.objects.filter(username__iexact=username).exists():
            raise DomainError("El nombre de usuario ya está en uso.", code="username_taken")

        try:
            validate_password(v["password"])
        except ValidationError as exc:
            raise DomainError(" ".join(exc.messages), code="weak_password") from exc

        grant_superuser = bool(v.get("is_superuser"))

        with transaction.atomic():
            user = User.objects.create_user(
                email=email,
                username=username,
                password=v["password"],
                is_staff=True,
                is_superuser=grant_superuser,
            )
            # Cuenta creada por un superusuario de confianza: se considera
            # el email ya verificado y no se le exige el circuito de alta.
            user.is_email_verified = True
            user.save(update_fields=["is_email_verified"])

        audit.record(
            AuditLog.Action.ADMIN_USER_CREATED,
            request=request,
            actor=request.user,
            target_type="user",
            target_id=user.pk,
            created_email=user.email,
            granted_superuser=grant_superuser,
        )

        return Response(
            {
                "message": "Administrador creado correctamente.",
                "user": _serialize_user(user),
            },
            status=status.HTTP_201_CREATED,
        )


class AdminUserDetailView(APIView):
    """
    PATCH /api/admin/users/<user_id>/ — Actualizar el estado de un usuario.

    Campos soportados: `is_active` (bloquear/desbloquear),
    `is_email_verified` (forzar verificación) y —solo para
    superusuarios— `is_staff` e `is_superuser`.
    """

    permission_classes = [IsAdminUser]

    # Campos cuya modificación implica elevar o reducir privilegios.
    _PRIVILEGE_FIELDS = ("is_staff", "is_superuser")

    @extend_schema(
        summary="Actualizar un usuario",
        request=UpdateUserSerializer,
        responses={
            200: OpenApiResponse(description="Usuario actualizado."),
            403: OpenApiResponse(description="Cambio de privilegios sin ser superusuario."),
            404: OpenApiResponse(description="Usuario no encontrado."),
        },
        tags=["Administración"],
    )
    def patch(self, request, user_id):
        serializer = UpdateUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        changes = serializer.validated_data

        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            raise DomainError(
                "Usuario no encontrado.",
                code="not_found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        touches_privileges = any(field in changes for field in self._PRIVILEGE_FIELDS)
        if touches_privileges and not request.user.is_superuser:
            raise DomainError(
                "Conceder o revocar privilegios requiere ser superusuario.",
                code="superuser_required",
                status_code=status.HTTP_403_FORBIDDEN,
            )

        self._guard_self_lockout(request.user, user, changes)
        self._guard_last_superuser(user, changes)

        for field, value in changes.items():
            setattr(user, field, bool(value))
        user.save(update_fields=list(changes.keys()))

        # Bloquear una cuenta debe echar fuera a quien la esté usando; sin
        # esto, `is_active=False` solo impedía nuevos logins y la sesión
        # ya abierta del usuario bloqueado seguía funcionando.
        if changes.get("is_active") is False:
            revoke_all_sessions(user)

        audit.record(
            AuditLog.Action.ADMIN_USER_UPDATED,
            request=request,
            actor=request.user,
            target_type="user",
            target_id=user.pk,
            target_email=user.email,
            changes={k: bool(val) for k, val in changes.items()},
        )

        return Response(
            {
                "message": "Usuario actualizado correctamente.",
                "user": _serialize_user(user),
            },
            status=status.HTTP_200_OK,
        )

    @staticmethod
    def _guard_self_lockout(actor: User, target: User, changes: dict) -> None:
        """Impedir que un administrador se bloquee o se degrade a sí mismo."""
        if actor.pk != target.pk:
            return
        if changes.get("is_active") is False:
            raise DomainError("No puedes bloquear tu propia cuenta.", code="self_lockout")
        if changes.get("is_staff") is False or changes.get("is_superuser") is False:
            raise DomainError(
                "No puedes revocar tus propios permisos de administrador.",
                code="self_demotion",
            )

    @staticmethod
    def _guard_last_superuser(target: User, changes: dict) -> None:
        """
        Impedir quedarse sin ningún superusuario activo.

        Es la contrapartida de `_guard_self_lockout`: sin esta regla, dos
        superusuarios podrían degradarse mutuamente y dejar la plataforma
        sin nadie capaz de conceder privilegios.
        """
        removes_superuser = changes.get("is_superuser") is False
        deactivates = changes.get("is_active") is False
        if not (removes_superuser or deactivates) or not target.is_superuser:
            return

        remaining = (
            User.objects.filter(is_superuser=True, is_active=True)
            .exclude(pk=target.pk)
            .exists()
        )
        if not remaining:
            raise DomainError(
                "No se puede dejar el sistema sin ningún superusuario activo.",
                code="last_superuser",
            )


class AdminResendVerificationView(APIView):
    """
    POST /api/admin/users/<user_id>/resend-verification/
    Reenviar el email de verificación a un usuario que aún no ha confirmado.
    """

    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Reenviar el email de verificación",
        request=None,
        responses={
            200: OpenApiResponse(description="Email reenviado."),
            400: OpenApiResponse(description="El usuario ya está verificado."),
            404: OpenApiResponse(description="Usuario no encontrado."),
        },
        tags=["Administración"],
    )
    def post(self, request, user_id):
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            raise DomainError(
                "Usuario no encontrado.",
                code="not_found",
                status_code=status.HTTP_404_NOT_FOUND,
            )

        if user.is_email_verified:
            raise DomainError(
                "El usuario ya tiene el email verificado.", code="already_verified"
            )

        dispatch_task(send_verification_email_task, user.pk)
        return Response(
            {"message": f"Email de verificación reenviado a {user.email}."},
            status=status.HTTP_200_OK,
        )


class AdminMarketSyncView(APIView):
    """
    POST /api/admin/market/sync/ — Forzar sincronización del catálogo CoinGecko.
    """

    permission_classes = [IsAdminUser]

    @extend_schema(
        summary="Sincronizar el catálogo de mercado",
        request=MarketSyncSerializer,
        responses={200: OpenApiResponse(description="Resultado de la sincronización.")},
        tags=["Administración"],
    )
    def post(self, request):
        serializer = MarketSyncSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        per_page = serializer.validated_data.get("per_page", 100)

        result = SyncMarketDataUseCase().execute(per_page=per_page)

        audit.record(
            AuditLog.Action.ADMIN_MARKET_SYNC,
            request=request,
            actor=request.user,
            per_page=per_page,
            assets_created=result.assets_created,
            assets_updated=result.assets_updated,
        )

        return Response(
            {
                "message": "Sincronización completada.",
                "assets_created": result.assets_created,
                "assets_updated": result.assets_updated,
                "snapshots_created": result.snapshots_created,
                "errors": result.errors,
            },
            status=status.HTTP_200_OK,
        )
