from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser
from core.infrastructure.persistence.models import User, CryptoAsset

class AdminUserListView(APIView):
    permission_classes = [IsAdminUser]

    def get(self, request):
        users = User.objects.all().order_by('-date_joined')
        data = [
            {
                "id": u.pk,
                "email": u.email,
                "username": u.username,
                "is_active": u.is_active,
                "is_email_verified": getattr(u, 'is_email_verified', False),
                "is_2fa_enabled": getattr(u, 'is_2fa_enabled', False),
                "is_admin": u.is_staff or u.is_superuser,
            }
            for u in users
        ]
        return Response(data, status=status.HTTP_200_OK)

    def post(self, request):
        email = request.data.get("email")
        username = request.data.get("username")
        password = request.data.get("password")

        if not email or not username or not password:
            return Response({"error": "Email, username y contraseña son requeridos"}, status=status.HTTP_400_BAD_REQUEST)
        
        if User.objects.filter(email=email).exists():
            return Response({"error": "El email ya está en uso"}, status=status.HTTP_400_BAD_REQUEST)

        # Crear el super usuario directamente 
        user = User.objects.create_superuser(email=email, username=username, password=password)
        # Opcional: auto-verificamos su correo para que pueda entrar de inmediato
        user.is_email_verified = True
        user.save()

        return Response({
            "message": "Administrador creado correctamente",
            "user": {
                "id": user.pk,
                "email": user.email,
                "username": user.username,
                "is_active": user.is_active,
                "is_email_verified": user.is_email_verified,
                "is_2fa_enabled": getattr(user, 'is_2fa_enabled', False),
                "is_admin": True
            }
        }, status=status.HTTP_201_CREATED)

class AdminUserDetailView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, user_id):
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return Response({"error": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        
        is_active = request.data.get("is_active")
        if is_active is not None:
            user.is_active = is_active

        is_admin = request.data.get("is_admin")
        if is_admin is not None:
            user.is_staff = is_admin
            user.is_superuser = is_admin
            
        user.save()
        
        return Response({"message": "Usuario actualizado correctamente"}, status=status.HTTP_200_OK)

class AdminMarketSyncView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        # Aquí se integraría la llamada real a CoinGecko o al proveedor de market data
        # Simularemos una operación de éxito.
        return Response({"message": "Data de mercado sincronizada..."}, status=status.HTTP_200_OK)
