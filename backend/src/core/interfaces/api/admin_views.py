"""
interfaces/api/admin_views.py — Endpoints de administración.

Todos los endpoints exigen IsAdminUser (is_staff). Reglas de negocio:
  - Un administrador no puede bloquearse ni quitarse permisos a sí mismo
    (evita dejar la plataforma sin administradores por accidente).
  - Las contraseñas de nuevos administradores pasan los validadores
    de Django (longitud, comunes, numéricas...).
"""

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser

from core.infrastructure.persistence.models import User
from core.application.use_cases.sync_market_data import SyncMarketDataUseCase
from core.tasks import dispatch_task
from core.tasks import send_verification_email as send_verification_email_task


def _serialize_user(u: User) -> dict:
    return {
        "id": u.pk,
        "email": u.email,
        "username": u.username,
        "is_active": u.is_active,
        "is_email_verified": u.is_email_verified,
        "is_2fa_enabled": u.is_2fa_enabled,
        "is_admin": u.is_staff or u.is_superuser,
        "date_joined": u.date_joined.isoformat(),
        "last_login": u.last_login.isoformat() if u.last_login else None,
    }


class AdminUserListView(APIView):
    """
    GET  /api/admin/users/?search=  — Listar usuarios (filtro opcional).
    POST /api/admin/users/          — Crear un nuevo administrador.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        users = User.objects.all().order_by("-date_joined")

        search = request.query_params.get("search", "").strip()
        if search:
            users = users.filter(
                Q(email__icontains=search) | Q(username__icontains=search)
            )

        return Response(
            [_serialize_user(u) for u in users],
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        email = (request.data.get("email") or "").strip().lower()
        username = (request.data.get("username") or "").strip()
        password = request.data.get("password") or ""

        if not email or not username or not password:
            return Response(
                {"error": "Email, username y contraseña son requeridos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(email=email).exists():
            return Response(
                {"error": "El email ya está en uso."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if User.objects.filter(username=username).exists():
            return Response(
                {"error": "El nombre de usuario ya está en uso."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            validate_password(password)
        except ValidationError as exc:
            return Response(
                {"error": " ".join(exc.messages)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user = User.objects.create_superuser(email=email, username=username, password=password)
        # Cuenta creada por un admin de confianza: email verificado de inmediato
        user.is_email_verified = True
        user.save(update_fields=["is_email_verified"])

        return Response(
            {
                "message": "Administrador creado correctamente.",
                "user": _serialize_user(user),
            },
            status=status.HTTP_201_CREATED,
        )


class AdminUserDetailView(APIView):
    """
    PATCH /api/admin/users/<user_id>/ — Actualizar estado de un usuario.

    Campos soportados: is_active (bloquear/desbloquear),
    is_admin (conceder/revocar permisos), is_email_verified (forzar verificación).
    """
    permission_classes = [IsAdminUser]

    def patch(self, request, user_id):
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "Usuario no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        is_active = request.data.get("is_active")
        is_admin = request.data.get("is_admin")
        is_email_verified = request.data.get("is_email_verified")

        # Protección: nadie puede bloquearse ni degradarse a sí mismo
        if user.pk == request.user.pk:
            if is_active is False:
                return Response(
                    {"error": "No puedes bloquear tu propia cuenta."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if is_admin is False:
                return Response(
                    {"error": "No puedes revocar tus propios permisos de administrador."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        update_fields = []
        if is_active is not None:
            user.is_active = bool(is_active)
            update_fields.append("is_active")

        if is_admin is not None:
            user.is_staff = bool(is_admin)
            user.is_superuser = bool(is_admin)
            update_fields.extend(["is_staff", "is_superuser"])

        if is_email_verified is not None:
            user.is_email_verified = bool(is_email_verified)
            update_fields.append("is_email_verified")

        if not update_fields:
            return Response(
                {"error": "No se ha indicado ningún campo a actualizar."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.save(update_fields=update_fields)

        return Response(
            {
                "message": "Usuario actualizado correctamente.",
                "user": _serialize_user(user),
            },
            status=status.HTTP_200_OK,
        )


class AdminResendVerificationView(APIView):
    """
    POST /api/admin/users/<user_id>/resend-verification/
    Reenviar el email de verificación a un usuario que aún no ha confirmado.
    """
    permission_classes = [IsAdminUser]

    def post(self, request, user_id):
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response(
                {"error": "Usuario no encontrado."},
                status=status.HTTP_404_NOT_FOUND,
            )

        if user.is_email_verified:
            return Response(
                {"error": "El usuario ya tiene el email verificado."},
                status=status.HTTP_400_BAD_REQUEST,
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

    def post(self, request):
        try:
            per_page = int(request.data.get("per_page", 100))
        except (ValueError, TypeError):
            return Response(
                {"error": "per_page debe ser un número entero."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        per_page = max(1, min(per_page, 250))
        result = SyncMarketDataUseCase().execute(per_page=per_page)
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
