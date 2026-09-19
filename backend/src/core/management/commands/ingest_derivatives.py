"""
ingest_derivatives — Archivar la microestructura de derivados.

    python manage.py ingest_derivatives BTC ETH
    python manage.py ingest_derivatives BTC --period 5m --limit 500
    python manage.py ingest_derivatives BTC --coverage

Pensado para correr periódicamente. Interés abierto, ratio long/short y taker
buy/sell traen hasta 30 días de pasado, así que una serie arranca con un mes de
historia el primer día; a partir de ahí la única fuente es este almacén.

La profundidad del libro NO tiene histórico de ninguna forma: si no se archiva,
no existe. Esa asimetría es el motivo de que este comando deba estar programado y
no ejecutarse a mano de vez en cuando — cada hora que no corre es una hora que no
se puede recuperar después.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from core.application.use_cases.derivatives_store import (
    IngestDerivativesUseCase, coverage,
)


class Command(BaseCommand):
    help = ("Trae y archiva interés abierto, ratio long/short, taker buy/sell y "
            "profundidad del libro, con sello point-in-time e idempotencia.")

    def add_arguments(self, parser):
        parser.add_argument("symbols", nargs="+", help="Símbolos, p. ej. BTC ETH")
        parser.add_argument("--venue", default="binance",
                            help="Venue de origen; forma parte de la clave.")
        parser.add_argument("--period", default="1h",
                            help="Granularidad de las series con histórico.")
        parser.add_argument("--limit", type=int, default=500,
                            help="Puntos a pedir por serie (máx. 500).")
        parser.add_argument("--coverage", action="store_true",
                            help="Solo informar de lo archivado, sin traer nada.")
        parser.add_argument("--json", action="store_true",
                            help="Volcar el resultado en JSON.")

    def handle(self, *args, **options):
        salidas = []
        for symbol in options["symbols"]:
            if options["coverage"]:
                salida = coverage(symbol, venue=options["venue"])
            else:
                salida = IngestDerivativesUseCase().execute(
                    symbol, venue=options["venue"], period=options["period"],
                    limit=options["limit"])
            salidas.append(salida)
            if not options["json"]:
                self._render(salida, es_cobertura=options["coverage"])

        if options["json"]:
            self.stdout.write(json.dumps(salidas, indent=2, ensure_ascii=False,
                                         default=str))

    # ------------------------------------------------------------------

    def _render(self, salida: dict, es_cobertura: bool) -> None:
        w = self.stdout.write
        w("")
        w(self.style.MIGRATE_HEADING(
            f"{salida.get('symbol', '?')} · {salida.get('venue', '?')}"))

        if es_cobertura:
            for metrica, datos in (salida.get("metrics") or {}).items():
                if datos.get("available"):
                    w(f"  {metrica:24s} {datos['points']:>6} puntos · "
                      f"{datos['span_days']:.1f} días")
                else:
                    w(self.style.WARNING(f"  {metrica:24s} {datos['note']}"))
            return

        w(f"  {salida.get('note', '')}")
        if salida.get("metrics"):
            w(f"  series: {', '.join(salida['metrics'])}")
        for metrica, error in (salida.get("errors") or {}).items():
            # Una fuente caída no frena a las demás, pero tiene que verse: una
            # ingesta silenciosamente incompleta es peor que una que falla.
            w(self.style.WARNING(f"  sin datos de {metrica} ({error})"))
