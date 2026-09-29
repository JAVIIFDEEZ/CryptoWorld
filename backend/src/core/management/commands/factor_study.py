"""
factor_study — ¿Le queda alfa a esto después de los factores de cripto?

    python manage.py factor_study
    python manage.py factor_study --strategy 12
    python manage.py factor_study --universe 30 --days 900 --json

Levanta los tres factores de Liu-Tsyvinski-Wu (*Common Risk Factors in
Cryptocurrency*, Journal of Finance 77(2), 2022) sobre el almacén OHLCV propio y,
si se le pasa una estrategia del libro, mide su alfa contra ellos.

Es el listón que faltaba. LTW midieron nueve estrategias long-short que por
separado daban retornos significativos; ajustadas por los tres factores, ninguna
conservaba alfa. Sin este contraste, un Sharpe alto puede ser beta de mercado
apalancada — y el mercado se compra sin pagar comisión de gestión.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from core.application.use_cases.factor_study import (
    DEFAULT_DAYS, DEFAULT_UNIVERSE, FactorStudyUseCase,
)


class Command(BaseCommand):
    help = ("Construye los factores de cripto (mercado, tamaño, momento) y mide "
            "el alfa de una estrategia contra ellos.")

    def add_arguments(self, parser):
        parser.add_argument("--strategy", type=int, default=None,
                            help="ID de StrategyDefinition cuya serie medir.")
        parser.add_argument("--universe", type=int, default=DEFAULT_UNIVERSE,
                            help="Activos del universo, por capitalización actual.")
        parser.add_argument("--days", type=int, default=DEFAULT_DAYS,
                            help="Días de velas diarias a cargar por activo.")
        parser.add_argument("--json", action="store_true",
                            help="Volcar el informe completo en JSON.")

    def handle(self, *args, **options):
        if options["universe"] < 10:
            raise CommandError(
                "Con menos de 10 activos un quintil tiene menos de dos miembros y "
                "el factor es ruido. El estudio se niega antes de producirlo.")

        returns = None
        if options["strategy"] is not None:
            returns = self._strategy_returns(options["strategy"])
            if returns is None:
                raise CommandError(
                    f"La estrategia {options['strategy']} no tiene serie de "
                    "retornos guardada en sus métricas de robustez.")

        report = FactorStudyUseCase().execute(
            strategy_returns=returns, days=options["days"],
            universe_size=options["universe"])

        if options["json"]:
            self.stdout.write(json.dumps(report, indent=2, ensure_ascii=False,
                                         default=str))
        else:
            self._render(report)

    # ------------------------------------------------------------------

    @staticmethod
    def _strategy_returns(strategy_id: int):
        from core.infrastructure.persistence.models import StrategyDefinition

        definicion = StrategyDefinition.objects.filter(id=strategy_id).first()
        if definicion is None:
            return None
        metricas = definicion.robustness_metrics or {}
        for clave in ("bar_returns", "returns", "oos_returns"):
            serie = metricas.get(clave)
            if isinstance(serie, list) and len(serie) >= 20:
                return serie
        return None

    def _render(self, report: dict) -> None:
        w = self.stdout.write
        w("")
        w(self.style.MIGRATE_HEADING("Factores de cripto · mercado / tamaño / momento"))

        cobertura = report.get("coverage") or {}
        if cobertura.get("available"):
            w(f"  {cobertura['symbols_used']} activos · {cobertura['weeks']} semanas")
            sin_datos = cobertura.get("symbols_without_data") or []
            if sin_datos:
                w(self.style.WARNING(f"  sin velas: {', '.join(sin_datos[:8])}"))
        else:
            w(self.style.WARNING(f"  {cobertura.get('note', 'sin cobertura')}"))

        if not report.get("available"):
            w(self.style.WARNING(f"  {report.get('note', '')}"))
            w("")
            return

        w("")
        w("  PRIMA DE CADA FACTOR")
        for nombre, datos in (report.get("factor_summary") or {}).items():
            if "annualized_pct" not in datos:
                continue
            # La t al lado del número: una media positiva con t de 0,3 no es una
            # prima, es ruido, y sin la t las dos se leen igual.
            w(f"    {nombre:6s} {datos['annualized_pct']:>8.2f} % anual   "
              f"t = {datos['t_stat']:+.2f}   ({datos['periods']} semanas)")

        alpha = report.get("alpha")
        if alpha and alpha.get("available"):
            w("")
            estilo = self.style.SUCCESS if alpha["verdict"] == "ALFA" else self.style.WARNING
            w(estilo(f"  ALFA: {alpha['verdict']}"))
            w(f"    {alpha['alpha_annualized_pct']:+.2f} % anual   "
              f"t = {alpha['alpha_t']:+.2f}   R² = {alpha['r_squared']}")
            w("    exposiciones: " + "  ".join(
                f"{k}={v:+.2f} (t={alpha['beta_t'][k]:+.1f})"
                for k, v in alpha["betas"].items()))
            w(f"    {alpha['note']}")
        elif alpha:
            w(self.style.WARNING(f"\n  ALFA: {alpha.get('note', '')}"))

        w("")
        w("  SESGOS QUE NO SE PUEDEN ELIMINAR CON ESTOS DATOS")
        w(f"    {report.get('survivorship_warning', '')}")
        factores = report.get("factors") or {}
        if factores.get("note"):
            w(f"    {factores['note']}")
        w("")
