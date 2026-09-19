"""
methodology.py — La nota metodológica, con los números de ESTA instalación.

El texto de las notas es genérico y vive en el dominio. Lo que añade este caso
de uso es lo que la hace verificable en vez de declarativa: cuántas
configuraciones se han probado de verdad, cuál es la campeona actual, y dónde
cae su Sharpe frente al que produciría el azar con ese mismo número de pruebas.

Esa última curva es el centro de la página. Un Sharpe sin el número de pruebas
que costó encontrarlo no es interpretable, y la forma más rápida de enseñarlo no
es un párrafo: es ver la campeona por encima o por debajo de la línea del azar.
"""

from __future__ import annotations

import logging

from core.domain.services import backtest_robustness as robustness
from core.domain.services import methodology as notes

logger = logging.getLogger(__name__)

# Varianza entre los Sharpe de las pruebas, usada para dibujar la curva cuando
# no hay una medida propia. No es un valor inventado: es el orden de magnitud
# habitual de la dispersión entre configuraciones de una misma búsqueda, y la
# respuesta dice explícitamente cuándo se ha usado este respaldo en lugar de la
# varianza observada, porque cambia cómo hay que leer la curva.
FALLBACK_SHARPE_VARIANCE = 1.0


class MethodologyUseCase:
    """Nota metodológica publicada, con el estado real del motor."""

    def execute(self, owner=None) -> dict:
        payload = {
            "version": notes.METHODOLOGY_VERSION,
            "golden_rule": notes.GOLDEN_RULE,
            "notes": notes.all_notes(),
            "disclaimers": list(notes.DISCLAIMERS),
        }
        payload.update(self._evidence(owner))
        return payload

    # ------------------------------------------------------------------

    def _evidence(self, owner) -> dict:
        """Los números propios: pruebas acumuladas, campeona y curva del azar."""
        try:
            from core.infrastructure.persistence.models import (
                StrategyDefinition, StrategyExperimentRun,
            )
        except Exception:  # noqa: BLE001 — sin persistencia la nota sigue siendo válida
            logger.info("methodology: sin persistencia disponible")
            return {"evidence_available": False}

        try:
            runs = StrategyExperimentRun.objects.all()
            total_runs = runs.count()
            total_evaluations = sum(r.evaluations for r in runs.only("evaluations"))
            effective = sum(r.effective_trials for r in runs.only("effective_trials"))

            champions = StrategyDefinition.objects.filter(passed_gating=True)
            if owner is not None:
                champions = champions.filter(owner=owner)
            champion = champions.order_by("-fitness").first()
        except Exception:  # noqa: BLE001
            logger.exception("methodology: no se pudo leer la evidencia")
            return {"evidence_available": False}

        champion_sharpe = None
        champion_name = None
        if champion is not None:
            champion_name = champion.name
            metrics = champion.robustness_metrics or {}
            for key in ("oos_sharpe", "sharpe", "sharpe_oos"):
                value = metrics.get(key)
                if isinstance(value, (int, float)):
                    champion_sharpe = float(value)
                    break

        # La varianza entre pruebas debería salir de las pruebas mismas. Mientras
        # no se persista, se usa el respaldo Y SE DICE: una curva dibujada con
        # una varianza supuesta sitúa la campeona en un sitio aproximado, y
        # presentarla como exacta sería el tipo de cifra que esta misma nota
        # critica en otras herramientas.
        variance = FALLBACK_SHARPE_VARIANCE
        curve = robustness.expected_max_sharpe_curve(
            variance=variance,
            n_trials=max(int(effective or total_evaluations or 1), 1),
            observed_sharpe=champion_sharpe,
        )

        return {
            "evidence_available": True,
            "runs_recorded": int(total_runs),
            "evaluations_total": int(total_evaluations),
            "effective_trials_total": int(effective),
            "champion_name": champion_name,
            "champion_sharpe": champion_sharpe,
            "expected_max_sharpe": curve,
            "variance_source": "FALLBACK",
            "evidence_note": (
                f"{total_evaluations:,} configuraciones evaluadas en {total_runs} "
                "ejecuciones registradas. La curva usa una varianza entre pruebas "
                "supuesta, no medida: sitúa a la campeona de forma aproximada y no "
                "debe leerse como un contraste exacto."
            ),
        }
