"""
calendar_study — ¿Qué eventos programados mueven de verdad a este activo?

    python manage.py calendar_study BTC
    python manage.py calendar_study BTC ETH --interval 4h
    python manage.py calendar_study BTC --families nfp expiry --json

Corre entero sobre el almacén propio de velas: no pide nada a ningún exchange, no
gasta cuota y funciona con la red caída.

Cómo se lee
───────────
El veredicto por familia responde a DOS preguntas y las separa a propósito:

  · `MUEVE_VOLATILIDAD` — el mercado se agita alrededor del evento. Es el
    resultado esperable y el más útil: marca ventanas en las que no conviene
    ejecutar, porque es cuando el diferencial se abre y el deslizamiento se come
    cualquier ventaja.
  · `MUEVE_DIRECCION` — el signo es sistemático. Es un hallazgo fuerte y raro, y
    antes de creérselo hay que comprobar que no viene de un único episodio.
  · `SIN_EFECTO_DETECTABLE` — no se detecta, que NO es lo mismo que no haberlo. El
    informe imprime el efecto mínimo detectable para que se vea la diferencia.
  · `SIN_POTENCIA` / `NO_IDENTIFICABLE` — no hay conclusión posible. La segunda es
    la más interesante: significa que el efecto del evento no se puede separar del
    efecto de su hora del día, y ninguna metodología lo arregla.

Los p-valores de todas las familias pasan por Benjamini-Hochberg antes de que
ninguno se llame efecto, porque ocho familias por dos preguntas son dieciséis
contrastes y quedarse con el más pequeño es el defecto clásico.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from core.application.use_cases.calendar_study import (
    DEFAULT_FDR, DEFAULT_LIMIT, CalendarStudyUseCase,
)
from core.domain.services import economic_calendar as cal
from core.domain.services import event_study as es


class Command(BaseCommand):
    help = ("Estudio de eventos sobre el calendario derivable por regla: mide si "
            "la volatilidad o la dirección del activo cambian alrededor de cada "
            "familia de eventos, contra un grupo de control que conserva la hora y "
            "el día de la semana.")

    def add_arguments(self, parser):
        parser.add_argument("symbols", nargs="+", help="Activos, p. ej. BTC ETH")
        parser.add_argument("--interval", default="1h",
                            help="Marco temporal de las velas del almacén.")
        parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                            help="Velas a leer por activo.")
        parser.add_argument("--families", nargs="*", default=None,
                            choices=sorted(cal.DERIVED_GENERATORS),
                            help=("Familias del calendario a estudiar. Por defecto, "
                                  "todas las derivables por regla."))
        parser.add_argument("--replicates", type=int, default=es.DEFAULT_REPLICATES,
                            help="Permutaciones del contraste.")
        parser.add_argument("--fdr", type=float, default=DEFAULT_FDR,
                            help=("Tasa de falsos descubrimientos de la corrección "
                                  "por multiplicidad."))
        parser.add_argument("--json", action="store_true",
                            help="Volcar el informe completo en JSON.")

    def handle(self, *args, **options):
        if options["replicates"] < 50:
            raise CommandError("Con menos de 50 permutaciones el p-valor más "
                               "pequeño posible es demasiado grueso para decidir.")
        if not 0 < options["fdr"] < 1:
            raise CommandError("La tasa de falsos descubrimientos ha de estar "
                               "entre 0 y 1.")

        use_case = CalendarStudyUseCase()
        informes = []
        for symbol in options["symbols"]:
            informe = use_case.execute(
                symbol, interval=options["interval"], limit=options["limit"],
                families=tuple(options["families"]) if options["families"] else None,
                replicates=options["replicates"], fdr=options["fdr"],
            )
            informes.append(informe)
            if not options["json"]:
                self._render(informe)

        if options["json"]:
            self.stdout.write(json.dumps(informes, indent=2, ensure_ascii=False,
                                         default=str))

    # ------------------------------------------------------------------

    def _render(self, informe: dict) -> None:
        w = self.stdout.write
        w("")
        w(self.style.MIGRATE_HEADING(
            f"{informe.get('symbol', '?')} · {informe.get('interval', '?')} · "
            f"eventos del calendario"))

        veredicto = informe.get("verdict", "?")
        estilo = (self.style.SUCCESS if veredicto == "CON_EFECTOS"
                  else self.style.WARNING)
        w(estilo(f"  VEREDICTO: {veredicto}"))
        w(f"  {informe.get('note', '')}")

        if informe.get("candles"):
            w("")
            w("  DATOS")
            w(f"    {informe['candles']} velas del almacén propio")
            w(f"    de {informe.get('first')} a {informe.get('last')}")
            calendario = informe.get("calendar") or {}
            if calendario.get("by_key"):
                w(f"    eventos derivados: " + ", ".join(
                    f"{k}×{v}" for k, v in calendario["by_key"].items()))
            if calendario.get("underivable"):
                w(self.style.WARNING(
                    f"    NO derivable por regla y por tanto ausente: "
                    f"{', '.join(sorted(calendario['underivable']))}"))

        familias = informe.get("families") or []
        if familias:
            w("")
            w("  FAMILIAS")
        for f in familias:
            self._render_family(f)

        if familias:
            w("")
            w("  PROTOCOLO")
            w(f"    {informe.get('protocol', '')}")
            w("")
            for linea in es.self_note().split("\n"):
                w(f"    {linea}")

    def _render_family(self, f: dict) -> None:
        w = self.stdout.write
        nombre = f.get("family", "?")
        veredicto = f.get("verdict", "?")
        marca = "*" if f.get("survives_fdr") else " "

        cabecera = (f"   {marca}{nombre:<26} {veredicto:<22} "
                    f"n={f.get('events_usable', 0)}")
        w(self.style.SUCCESS(cabecera) if f.get("survives_fdr") else cabecera)

        if veredicto in ("SIN_POTENCIA", "NO_IDENTIFICABLE", "SIN_DATOS"):
            w(f"       {f.get('note', '')}")
            if f.get("hint", {}).get("why"):
                w(f"       por qué se estudia así: {f['hint']['why']}")
            return

        obs = f.get("observed") or {}
        ctrl = f.get("control") or {}
        w(f"       volatilidad {obs.get('vol_ratio_mean', 0):.2f}× vs control "
          f"{ctrl.get('vol_ratio_mean', 0):.2f}×   p={f.get('p_volatility', 1):.4f}")
        w(f"       |movimiento| {obs.get('car_abs_mean', 0) * 100:.2f} % vs control "
          f"{ctrl.get('car_abs_mean', 0) * 100:.2f} %   p={f.get('p_direction', 1):.4f}")
        mde = f.get("minimum_detectable_car")
        if mde is not None and mde == mde:
            w(f"       efecto mínimo detectable con {obs.get('n', 0)} eventos: "
              f"{mde * 100:.2f} %")
        if f.get("survives_fdr"):
            w(f"       sobrevive a la corrección por multiplicidad en: "
              f"{', '.join(f.get('survives_questions') or [])}")
        else:
            w(f"       no sobrevive a la corrección sobre {f.get('fdr_tests', 0)} "
              f"contrastes")
