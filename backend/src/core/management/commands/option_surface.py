"""
option_surface — Qué dice el mercado de opciones que va a pasar.

    python manage.py option_surface BTC
    python manage.py option_surface BTC ETH --no-persist
    python manage.py option_surface BTC --vov
    python manage.py option_surface BTC --json

Momentos implícitos del vencimiento más cercano a 30 días, desde la API pública
de Deribit: varianza libre de modelo, risk reversal y butterfly a 25 delta, y la
prima de riesgo de varianza contra la volatilidad realizada del propio almacén.

Es la única fuente que da una medida PROSPECTIVA de volatilidad de cripto sin
pagar un proveedor de datos — y la volatilidad es, según el propio `edge_test`, la
única pregunta que esta muestra puede responder.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from core.application.use_cases.option_surface import OptionSurfaceUseCase, vol_of_vol


class Command(BaseCommand):
    help = ("Calcula los momentos implícitos de la superficie de opciones de "
            "Deribit y los archiva como serie.")

    def add_arguments(self, parser):
        parser.add_argument("currencies", nargs="*", default=["BTC"],
                            help="Monedas con mercado de opciones (BTC, ETH).")
        parser.add_argument("--no-persist", action="store_true",
                            help="Calcular sin archivar.")
        parser.add_argument("--vov", action="store_true",
                            help="Informar de la volatilidad de la volatilidad.")
        parser.add_argument("--realized", type=float, default=None,
                            help=("Volatilidad realizada anualizada, en fracción, "
                                  "para calcular la prima de varianza."))
        parser.add_argument("--json", action="store_true",
                            help="Volcar el informe en JSON.")

    def handle(self, *args, **options):
        salidas = []
        for moneda in options["currencies"] or ["BTC"]:
            if options["vov"]:
                salida = vol_of_vol(moneda)
                salida["currency"] = moneda.upper()
            else:
                salida = OptionSurfaceUseCase().execute(
                    moneda, realized_vol_annual=options["realized"],
                    persist=not options["no_persist"])
            salidas.append(salida)
            if not options["json"]:
                self._render(salida, es_vov=options["vov"])

        if options["json"]:
            self.stdout.write(json.dumps(salidas, indent=2, ensure_ascii=False,
                                         default=str))

    # ------------------------------------------------------------------

    def _render(self, salida: dict, es_vov: bool) -> None:
        w = self.stdout.write
        w("")
        w(self.style.MIGRATE_HEADING(
            f"{salida.get('currency', '?')} · superficie de opciones"))

        if not salida.get("available"):
            w(self.style.WARNING(f"  {salida.get('note', 'sin datos')}"))
            w("")
            return

        if es_vov:
            w(f"  volatilidad implícita media: {salida['iv_mean_pct']:.2f} %")
            w(f"  volatilidad de la volatilidad: {salida['vov']:.4f}"
              f"  ({salida['vov_pct_of_iv']:.1f} % de la implícita)")
            w(f"  sobre {salida['points']} lecturas de {salida['days']} días")
            w(f"  {salida['note']}")
            w("")
            return

        v = salida["variance"]
        w(f"  subyacente {salida['underlying_price']:,.0f} · vencimiento en "
          f"{salida['days_to_expiry']:.1f} días · {salida['expiries_available']} "
          "vencimientos cotizados")
        w("")
        w("  VOLATILIDAD IMPLÍCITA")
        w(f"    {v['implied_vol_annual_pct']:.2f} % anual  "
          f"({v['n_strikes']} strikes, {v['strike_range'][0]:,.0f}–{v['strike_range'][1]:,.0f})")
        # La cobertura en sigmas es lo que permite juzgar el sesgo de truncación:
        # lo que queda fuera de la cadena SIEMPRE resta varianza.
        w(f"    cadena cubre {v['coverage_sigma_down']:.1f}σ abajo y "
          f"{v['coverage_sigma_up']:.1f}σ arriba — lo que falta infravalora")

        alas = salida.get("wings") or {}
        w("")
        w("  ALAS (25 delta)")
        if alas.get("available"):
            w(f"    call {alas['iv_call_pct']:.2f} %   put {alas['iv_put_pct']:.2f} %"
              f"   dinero {alas['iv_atm_pct']:.2f} %")
            estilo = self.style.WARNING if alas["risk_reversal_pct"] < 0 else self.style.SUCCESS
            w(estilo(f"    risk reversal {alas['risk_reversal_pct']:+.2f} pts "
                     f"→ sesgo {alas['skew_side']}"))
            if alas.get("butterfly_pct") is not None:
                w(f"    butterfly {alas['butterfly_pct']:+.2f} pts (convexidad)")
        else:
            w(self.style.WARNING(f"    {alas.get('note', 'no disponibles')}"))

        vrp = salida.get("vrp")
        if vrp and vrp.get("available"):
            w("")
            w("  PRIMA DE RIESGO DE VARIANZA")
            w(f"    implícita {vrp['implied_vol_pct']:.2f} % vs realizada "
              f"{vrp['realized_vol_pct']:.2f} %  →  {vrp['vrp_vol_points']:+.2f} pts "
              f"(ratio {vrp['iv_rv_ratio']})")
            w(f"    {vrp['note']}")

        if salida.get("stored") is not None:
            w("")
            w(f"  archivados {salida['stored']} puntos nuevos")
        w("")
        w(f"  {salida['note']}")
        w("")
