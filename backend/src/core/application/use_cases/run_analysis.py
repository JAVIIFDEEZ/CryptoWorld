"""
run_analysis.py — Caso de uso: Ejecutar análisis cuantitativo.

Estructura base preparada para ampliar en fases posteriores del TFG.
Por ahora crea y persiste el registro del análisis en estado 'pending'.

En fases siguientes aquí se invocarán los servicios de análisis:
RSI, MACD, Bollinger Bands, etc.
"""

from core.domain.entities.crypto_asset import AnalysisExecutionEntity
from core.application.dto.asset_dto import AnalysisRequestInputDTO, AnalysisOutputDTO


class RunAnalysisUseCase:
    """
    Caso de uso: iniciar ejecución de un análisis técnico.

    Estructura vacía preparada para recibir implementación en
    fases de análisis cuantitativo del TFG.
    """

    def execute(self, input_dto: AnalysisRequestInputDTO) -> AnalysisOutputDTO:
        """
        Registrar solicitud de análisis.

        En este momento solo crea la entidad en estado 'pending'.
        La lógica de análisis real se implementará en futuras iteraciones.
        """
        # Crear entidad de ejecución en el dominio
        execution = AnalysisExecutionEntity(
            asset_symbol=input_dto.asset_symbol,
            analysis_type=input_dto.analysis_type,
            status="pending",
        )

        # TODO: Inyectar repositorio y persistir la ejecución
        # TODO: Disparar tarea asíncrona (Celery) con el análisis real

        return AnalysisOutputDTO(
            id=0,  # Placeholder hasta implementar persistencia
            asset_symbol=execution.asset_symbol,
            analysis_type=execution.analysis_type,
            status=execution.status,
            result=None,
        )
