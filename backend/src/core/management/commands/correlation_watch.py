"""
correlation_watch — ¿Sigue existiendo la diversificación de la cartera?

    python manage.py correlation_watch BTC ETH SOL
    python manage.py correlation_watch BTC ETH SOL --interval 4h --drop 0.20
    python manage.py correlation_watch BTC ETH --json > corr.json

Corre entero sobre el almacén propio de velas: no pide nada a ningún exchange,
así que funciona con la red caída y no gasta cuota. Lo que decide es si la
correlación entre las patas de la cartera ha CAMBIADO respecto al tramo tranquilo
del propio histórico, con un umbral calibrado contra el nulo de cada pareja en vez
de puesto a mano.

Por qué un comando y no un endpoint
───────────────────────────────────
Igual que `carry_test` y `edge_test`: esto es una herramienta para decidir sobre
capital propio, y colgarla de la API la convertiría en una señal mostrada a
terceros, que es otra cosa y con otro perímetro.

Cómo se lee la salida
─────────────────────
El retardo importa más que el veredicto. Medido sobre rupturas plantadas, una
caída de correlación de 0,80 a 0,30 se detecta en unas 33 barras y una de 0,80 a
0,65 en unas 121, con el 90 % de detección. Así que un ESTABLE sobre un tramo
vigilado corto no dice «no ha cambiado»: dice «todavía no había datos para
verlo». El informe imprime las dos cosas.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from core.application.use_cases.correlation_watch import (
    DEFAULT_LIMIT, DEFAULT_REFERENCE_FRAC, CorrelationWatchUseCase,
)
from core.domain.services import structural_break as sb


class Command(BaseCommand):
    help = ("Vigila rupturas de correlación entre activos con un CUSUM sobre la z "
            "de Fisher de la correlación móvil, desvolatilizada, y un umbral "
            "calibrado contra el nulo de correlación constante de cada pareja.")

    def add_arguments(self, parser):
        parser.add_argument("symbols", nargs="+", help="Activos, p. ej. BTC ETH SOL")
        parser.add_argument("--interval", default="1h",
                            help="Marco temporal de las velas del almacén.")
        parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT,
                            help="Velas a leer por activo.")
        parser.add_argument("--window", type=int, default=sb.DEFAULT_CORR_WINDOW,
                            help=("Ventana de la correlación móvil, en barras. Más "
                                  "larga estima con menos ruido y avisa más tarde."))
        parser.add_argument("--drop", type=float, default=sb.DEFAULT_DETECT_DROP,
                            help=("Caída de correlación que se quiere cazar pronto. "
                                  "De aquí sale la holgura del CUSUM: no es un "
                                  "filtro posterior, cambia el detector."))
        parser.add_argument("--alpha", type=float, default=sb.DEFAULT_ALPHA,
                            help=("Falsa alarma admitida en TODA la ventana "
                                  "vigilada, no por barra."))
        parser.add_argument("--reference", type=float, default=DEFAULT_REFERENCE_FRAC,
                            help="Fracción del histórico que hace de tramo tranquilo.")
        parser.add_argument("--replicates", type=int, default=sb.DEFAULT_REPLICATES,
                            help=("Réplicas del nulo con las que se calibra el "
                                  "umbral. Subirlas no mejora la tasa medida: el "
                                  "exceso viene del nulo, no del Monte Carlo."))
        parser.add_argument("--family-wise", action="store_true",
                            help=("Reparte el α entre todas las parejas, de modo "
                                  "que sea la falsa alarma de la cartera COMPLETA "
                                  "y no de cada pareja. Cuesta potencia."))
        parser.add_argument("--json", action="store_true",
                            help="Volcar el informe completo en JSON.")

    def handle(self, *args, **options):
        if len(options["symbols"]) < 2:
            raise CommandError("Hacen falta al menos dos activos para una correlación.")
        if not 0 < options["alpha"] < 0.5:
            raise CommandError("El alfa ha de estar entre 0 y 0,5.")
        if not 0 < options["drop"] < 2:
            raise CommandError("La caída objetivo ha de estar entre 0 y 2.")
        if options["window"] < sb.MIN_CORR_WINDOW:
            raise CommandError(f"La ventana mínima es {sb.MIN_CORR_WINDOW} barras: "
                               f"por debajo, la correlación es ruido.")
        if options["replicates"] < 20:
            raise CommandError("Con menos de 20 réplicas no se puede calibrar un "
                               "umbral, y devolver uno sería peor que no darlo.")

        informe = CorrelationWatchUseCase().execute(
            options["symbols"], interval=options["interval"], limit=options["limit"],
            window=options["window"], detect_drop=options["drop"],
            alpha=options["alpha"], reference_frac=options["reference"],
            replicates=options["replicates"], family_wise=options["family_wise"],
        )

        if options["json"]:
            self.stdout.write(json.dumps(informe, indent=2, ensure_ascii=False,
                                         default=str))
        else:
            self._render(informe)

    # ------------------------------------------------------------------

    def _render(self, informe: dict) -> None:
        w = self.stdout.write
        w("")
        w(self.style.MIGRATE_HEADING(
            f"Correlaciones · {informe.get('interval', '?')} · "
            f"{', '.join(informe.get('symbols') or []) or 'sin activos'}"))

        veredicto = informe.get("verdict", "?")
        estilo = (self.style.SUCCESS if veredicto == "ESTABLE"
                  else self.style.WARNING if veredicto in ("INDICIOS", "SIN_DATOS")
                  else self.style.ERROR)
        w(estilo(f"  VEREDICTO: {veredicto}"))
        w(f"  {informe.get('note', '')}")

        if informe.get("missing"):
            w(self.style.WARNING(
                f"  sin histórico en el almacén: {', '.join(informe['missing'])}"))

        if informe.get("candles_aligned"):
            w("")
            w("  DATOS")
            w(f"    {informe['candles_aligned']} velas comunes a todos los activos, "
              f"unidas por marca temporal")
            w(f"    de {informe.get('first')} a {informe.get('last')}")
            w(f"    ventana {informe.get('window')} barras · caída objetivo "
              f"{informe.get('detect_drop')} · α {informe.get('alpha')}"
              + (f" repartido entre parejas → {informe.get('alpha_per_pair'):.2%} "
                 f"cada una" if informe.get("family_wise") else " por pareja"))

        parejas = informe.get("pairs") or []
        if parejas:
            w("")
            w("  PAREJAS")
        for p in parejas:
            self._render_pair(p)

        if parejas:
            w("")
            w("  PROTOCOLO")
            w(f"    {informe.get('protocol', '')}")
            w("")
            for linea in sb.self_note().split("\n"):
                w(f"    {linea}")

    def _render_pair(self, p: dict) -> None:
        w = self.stdout.write
        nombre = p.get("pair", "?")
        veredicto = p.get("verdict", "?")

        if veredicto == "SIN_DATOS":
            w(f"    {nombre:<14} SIN_DATOS   {p.get('note', '')}")
            return

        ref = p.get("reference_corr")
        rec = p.get("recent_corr")
        cabecera = (f"    {nombre:<14} {veredicto:<9} "
                    f"referencia {ref:+.2f} → reciente {rec:+.2f}"
                    if ref is not None and rec is not None
                    else f"    {nombre:<14} {veredicto:<9}")
        w(self.style.ERROR(cabecera) if p.get("broken") else cabecera)

        w(f"       estadístico {p.get('peak', 0.0):>7.1f} vs umbral "
          f"{p.get('threshold') or 0.0:>7.1f}   "
          f"(ventanas independientes en la referencia: "
          f"{p.get('independent_windows', 0)})")
        if p.get("broken"):
            w(f"       alarma en {p.get('alarm_time')} · brazo de "
              f"{p.get('direction')}")
            w(f"       punto de cambio estimado: {p.get('change_point_time')} "
              f"({p.get('detection_delay')} barras antes de la alarma)")
            w("       el estimador del punto de cambio llega unas barras TARDE: "
              "no es una cota del suceso")
