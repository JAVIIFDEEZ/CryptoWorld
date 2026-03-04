"""
repositories_impl.py — Implementaciones concretas de los repositorios.

Esta capa es el puente entre las interfaces del dominio y Django ORM.
Implementa los contratos abstractos definidos en domain/repositories/.

Principio aplicado: Inversión de Dependencias (DIP).
Los casos de uso usan IUserRepository; aquí está DjangoUserRepository
que implementa esa interfaz usando Django ORM.

Si en el futuro quisiéramos cambiar a MongoDB, solo se cambia
esta implementación, sin tocar ni el dominio ni los casos de uso.
"""

from typing import Optional, List
from decimal import Decimal

from core.domain.repositories.user_repository import IUserRepository
from core.domain.repositories.crypto_asset_repository import ICryptoAssetRepository
from core.domain.entities.user import UserEntity
from core.domain.entities.crypto_asset import CryptoAssetEntity
from core.infrastructure.persistence.models import User as UserModel
from core.infrastructure.persistence.models import CryptoAsset as CryptoAssetModel


class DjangoUserRepository(IUserRepository):
    """
    Implementación del repositorio de usuarios usando Django ORM.

    Traduce entre el modelo ORM (infraestructura) y la entidad
    de dominio (UserEntity). La capa de aplicación nunca toca
    el modelo ORM directamente.
    """

    def get_by_id(self, user_id: int) -> Optional[UserEntity]:
        try:
            model = UserModel.objects.get(pk=user_id)
            return self._to_entity(model)
        except UserModel.DoesNotExist:
            return None

    def get_by_email(self, email: str) -> Optional[UserEntity]:
        try:
            model = UserModel.objects.get(email=email)
            return self._to_entity(model)
        except UserModel.DoesNotExist:
            return None

    def save(self, user: UserEntity) -> UserEntity:
        """
        Persistir una entidad de usuario.
        Si tiene id: actualizar. Si no: crear.
        """
        if user.id:
            model = UserModel.objects.get(pk=user.id)
            model.email = user.email
            model.username = user.username
            model.is_active = user.is_active
            model.is_staff = user.is_staff
            model.save()
        else:
            # create_user gestiona el hash de contraseña automáticamente
            # La contraseña viene del caso de uso a través del view
            model = UserModel.objects.create_user(
                email=user.email,
                username=user.username,
            )

        return self._to_entity(model)

    def exists_by_email(self, email: str) -> bool:
        return UserModel.objects.filter(email=email).exists()

    def get_model_by_id(self, user_id: int) -> Optional[UserModel]:
        """Devuelve el modelo ORM directamente. Útil para operaciones de bajo nivel."""
        try:
            return UserModel.objects.get(pk=user_id)
        except UserModel.DoesNotExist:
            return None

    def set_email_verified(self, user_id: int) -> None:
        """Marcar el email del usuario como verificado."""
        UserModel.objects.filter(pk=user_id).update(is_email_verified=True)

    def set_password(self, user_id: int, raw_password: str) -> None:
        """Cambiar la contraseña de un usuario. Django hashea automáticamente."""
        model = UserModel.objects.get(pk=user_id)
        model.set_password(raw_password)
        model.save(update_fields=["password"])

    def set_totp_secret(self, user_id: int, secret: Optional[str]) -> None:
        """Guardar (o borrar) el secreto TOTP de un usuario."""
        UserModel.objects.filter(pk=user_id).update(totp_secret=secret)

    def set_2fa_enabled(self, user_id: int, enabled: bool) -> None:
        """Activar o desactivar 2FA para un usuario."""
        UserModel.objects.filter(pk=user_id).update(is_2fa_enabled=enabled)

    @staticmethod
    def _to_entity(model: UserModel) -> UserEntity:
        """Convertir modelo ORM → entidad de dominio."""
        return UserEntity(
            id=model.pk,
            email=model.email,
            username=model.username,
            is_active=model.is_active,
            is_staff=model.is_staff,
            is_email_verified=model.is_email_verified,
            totp_secret=model.totp_secret,
            is_2fa_enabled=model.is_2fa_enabled,
        )


class DjangoCryptoAssetRepository(ICryptoAssetRepository):
    """
    Implementación del repositorio de activos criptográficos usando Django ORM.
    """

    def get_all(self) -> List[CryptoAssetEntity]:
        models = CryptoAssetModel.objects.all()
        return [self._to_entity(m) for m in models]

    def get_by_symbol(self, symbol: str) -> Optional[CryptoAssetEntity]:
        try:
            model = CryptoAssetModel.objects.get(symbol=symbol.upper())
            return self._to_entity(model)
        except CryptoAssetModel.DoesNotExist:
            return None

    def save(self, asset: CryptoAssetEntity) -> CryptoAssetEntity:
        model, _ = CryptoAssetModel.objects.update_or_create(
            symbol=asset.symbol,
            defaults={
                "name": asset.name,
                "current_price": asset.current_price,
                "market_cap": asset.market_cap,
                "volume_24h": asset.volume_24h,
                "price_change_24h": asset.price_change_24h,
            }
        )
        return self._to_entity(model)

    @staticmethod
    def _to_entity(model: CryptoAssetModel) -> CryptoAssetEntity:
        """Convertir modelo ORM → entidad de dominio."""
        return CryptoAssetEntity(
            id=model.pk,
            symbol=model.symbol,
            name=model.name,
            current_price=Decimal(str(model.current_price)),
            market_cap=Decimal(str(model.market_cap)) if model.market_cap else None,
            volume_24h=Decimal(str(model.volume_24h)) if model.volume_24h else None,
            price_change_24h=Decimal(str(model.price_change_24h)) if model.price_change_24h else None,
        )
