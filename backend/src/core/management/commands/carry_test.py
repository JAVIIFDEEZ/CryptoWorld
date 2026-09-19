"""
carry_test — ¿Sobrevive el carry de este activo a sus costes y a un shock?

    python manage.py carry_test BTC
    python manage.py carry_test BTC ETH --notional 25000 --margin 0.3
    python manage.py carry_test BTC --json > btc_carry.json

El gemelo de `edge_test` para la otra mitad del documento. Aquel decide qué
pregunta puede responder la muestra; este decide si un flujo de caja contractual
queda en pie después de pagar lo que cuesta cobrarlo.

Por qué un comando y no un endpoint
───────────────────────────────────
El carry es alfa operable con capital propio, no una función del producto.
Colgarlo de la API lo convertiría en una recomendación de inversión mostrada a
terceros, que es otra cosa y con otro perímetro. Aquí es una herramienta de quien
opera su propia cuenta.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from core.application.use_cases.carry_test import (
    DEFAULT_NOTIONAL_USD, DEFAULT_SHOCK_PCT, CarryTestUseCase,
)


class Command(BaseCommand):
    help = ("Mide el carry delta-neutral (spot largo + perpetuo corto) sobre el "
            "funding histórico real, con las cuatro comisiones, el coste de "
            "capital, un nulo por aleatorización de signo y una prueba de shock.")

    def add_arguments(self, parser):
        parser.add_argument("symbols", nargs="+", help="Símbolos, p. ej. BTC ETH")
        parser.add_argument("--notional", type=float, default=DEFAULT_NOTIONAL_USD,
                            help="Nocional por pata, en USD.")
        parser.add_argument("--margin", type=float, default=0.20,
                            help=("Fracción del nocional como margen de la pata "
                                  "corta. Menos margen es más capital eficiente y "
                                  "más cerca de la liquidación."))
        parser.add_argument("--shock", type=float, default=DEFAULT_SHOCK_PCT,
                            help="Salto de precio, en %%, contra el que probar el margen.")
        parser.add_argument("--fee", type=float, default=5.0,
                            help="Comisión taker por orden, en puntos básicos.")
        parser.add_argument("--slippage", type=float, default=2.0,
                            help="Deslizamiento por orden, en puntos básicos.")
        parser.add_argument("--capital-cost", type=float, default=0.0,
                            help="Coste de oportunidad del capital, anualizado en %%.")
        parser.add_argument("--days", type=int, default=365,
                            help="Días de histórico de financiación a considerar.")
        parser.add_argument("--json", action="store_true",
                            help="Volcar el informe completo en JSON.")

    def handle(self, *args, **options):
        if options["notional"] <= 0:
            raise CommandError("El nocional ha de ser positivo.")
        if not 0 < options["margin"] <= 1:
            raise CommandError("El margen ha de estar entre 0 y 1.")

        use_case = CarryTestUseCase()
        informes = []
        for symbol in options["symbols"]:
            report = use_case.execute(
                symbol, notional_usd=options["notional"],
                margin_pct=options["margin"], shock_pct=options["shock"],
                taker_fee_bps=options["fee"], slippage_bps=options["slippage"],
                capital_cost_annual_pct=options["capital_cost"],
                days=options["days"],
            )
            informes.append(report)
            if not options["json"]:
                self._render(report)

        if options["json"]:
            self.stdout.write(json.dumps(informes, indent=2, ensure_ascii=False,
                                         default=str))

    # ------------------------------------------------------------------

    def _render(self, report: dict) -> None:
        w = self.stdout.write
        w("")
        w(self.style.MIGRATE_HEADING(f"{report.get('symbol', '?')} · carry delta-neutral"))

        veredicto = report.get("verdict", "?")
        estilo = self.style.SUCCESS if report.get("tradeable") else self.style.WARNING
        w(estilo(f"  VEREDICTO: {veredicto}"))
        w(f"  {report.get('note', '')}")

        cobertura = report.get("funding_coverage") or {}
        w("")
        w("  FINANCIACIÓN")
        w(f"    {cobertura.get('note', '')}")
        if cobertura.get("available"):
            w(f"    de {cobertura.get('first')} a {cobertura.get('last')}")

        obs = report.get("observed") or {}
        if obs.get("periods"):
            w("")
            w("  RESULTADO")
            w(f"    bruto de financiación .... {obs['gross_funding_usd']:>12,.2f} USD")
            w(f"    comisiones (4 órdenes) ... {-obs['order_costs_usd']:>12,.2f} USD"
              f"   [{obs['round_trip_bps']:.0f} bps ida y vuelta]")
            w(f"    coste de capital ......... {-obs['capital_cost_usd']:>12,.2f} USD")
            w(f"    NETO ..................... {obs['net_usd']:>12,.2f} USD")
            w(f"    sobre {obs['capital_usd']:,.0f} USD inmovilizados durante "
              f"{obs['years']:.2f} años → {obs['net_annualized_pct']:+.2f} % anual")
            w(f"    periodos cobrando: {obs['positive_periods_pct']:.0f} % de {obs['periods']}")

        nulo = report.get("null") or {}
        if nulo.get("p95_usd") is not None:
            w("")
            w("  CONTRA EL NULO")
            w(f"    percentil 95 de un funding sin sesgo: {nulo['p95_usd']:>10,.2f} USD")
            w(f"    mediana del nulo ...................: {nulo['median_usd']:>10,.2f} USD")
            w(f"    {nulo['note']}")

        shock = report.get("shock") or {}
        if shock:
            w("")
            w("  MARGEN")
            w(f"    {shock.get('note', '')}")
            if obs.get("liquidation_price"):
                w(f"    precio de liquidación de la pata corta: {obs['liquidation_price']:,.2f}")

        w("")
        w("  PROTOCOLO")
        w(f"    {report.get('protocol', '')}")
        w("")
