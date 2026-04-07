"""
admin_get_stats.py — Caso de uso: Obtener estadísticas del sistema (admin).
"""

from core.application.dto.admin_dto import AdminStatsOutputDTO
from core.infrastructure.persistence.models import (
    User as UserModel,
    CryptoAsset as CryptoAssetModel,
    AnalysisExecution as AnalysisExecutionModel,
)


class AdminGetStatsUseCase:
    """
    Caso de uso: obtener métricas globales del sistema.
    Usa queries directas al ORM por eficiencia en agregaciones.
    """

    def execute(self) -> AdminStatsOutputDTO:
        total_users = UserModel.objects.count()
        active_users = UserModel.objects.filter(is_active=True).count()
        verified_users = UserModel.objects.filter(is_email_verified=True).count()
        users_with_2fa = UserModel.objects.filter(is_2fa_enabled=True).count()
        admin_users = UserModel.objects.filter(role="admin").count()
        total_assets = CryptoAssetModel.objects.count()
        total_analyses = AnalysisExecutionModel.objects.count()

        return AdminStatsOutputDTO(
            total_users=total_users,
            active_users=active_users,
            verified_users=verified_users,
            users_with_2fa=users_with_2fa,
            admin_users=admin_users,
            total_assets=total_assets,
            total_analyses=total_analyses,
        )
