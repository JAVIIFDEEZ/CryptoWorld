"""
seasonality — ¿Hay horas del mercado que no son como las demás?

    python manage.py seasonality BTC
    python manage.py seasonality BTC ETH --interval 1h --json

Corre entero sobre el almacén propio de velas: no pide nada a ningún exchange.

Para qué sirve
─────────────
Cripto opera 24/7, lo cual se suele leer como «no hay sesiones» — y es lo
contrario de lo que pasa: los solapes de Asia, Europa y Estados Unidos siguen ahí,
solo que nadie cierra. Si hay horas sistemáticamente más convulsas, eso cambia
tres cosas concretas: cuándo NO colocar una orden grande, cuándo un stop tiene más
probabilidad de saltar por ruido, y qué variables tienen sentido en el modelo.

Y una cuarta, que es de dónde salió este módulo: el estudio de eventos necesita
controlar el efecto de la hora del día para no atribuírselo al evento. Aquí ese
confusor se mide en vez de solo controlarse.

Cómo se lee
───────────
La salida NO es una lista de 168 números. Son 168 contrastes y al 5 % por casilla
ocho saldrían significativas sin que haya nada, así que el orden es:

  1. **Contraste global.** ¿Hay alguna estructura de hora de la semana? Si no
     pasa, las casillas no se miran, porque cualquier cosa que se encontrara ahí
     sería una de las ocho.
  2. **Si pasa, las casillas con Benjamini-Hochberg**, y se dice cuántas
     sobreviven de cuántas se probaron.

Una casilla marcada NO es una oportunidad: más movimiento con dirección
impredecible significa más deslizamiento y más stops saltados por ruido, así que
el uso correcto es evitarla.
"""

from __future__ import annotations

import json

import numpy as np
from django.core.management.base import BaseCommand, CommandError

from core.domain.services import seasonality as sn


class Command(BaseCommand):
    help = ("Rejilla de 7 días × 24 horas de actividad y dirección, con contraste "
            "global antes que las casillas y corrección por multiplicidad entre "
            "ellas. Nulo por permutación de bloques contra las mismas etiquetas "
            "horarias.")

    def add_arguments(self, parser):
        parser.add_argument("symbols", nargs="+", help="Activos, p. ej. BTC ETH")
        parser.add_argument("--interval", default="1h",
                            help=("Marco temporal. La rejilla es horaria, así que "
                                  "marcos más largos dejan casillas vacías."))
        parser.add_argument("--limit", type=int, default=30_000,
                            help="Velas a leer por activo.")
        parser.add_argument("--rotations", type=int, default=sn.DEFAULT_ROTATIONS,
                            help="Réplicas del nulo por permutación de bloques.")
        parser.add_argument("--block", type=int, default=sn.DEFAULT_BLOCK,
                            help=("Longitud del bloque, en velas. Tiene que ser "
                                  "coprima con 168."))
        parser.add_argument("--fdr", type=float, default=sn.DEFAULT_FDR,
                            help="Tasa de falsos descubrimientos entre casillas.")
        parser.add_argument("--json", action="store_true",
                            help="Volcar el informe completo en JSON.")

    def handle(self, *args, **options):
        from math import gcd

        if options["rotations"] < 100:
            raise CommandError("Con menos de 100 réplicas el contraste global no "
                               "tiene resolución para el nivel que promete.")
        if not 0 < options["fdr"] < 1:
            raise CommandError("La tasa de falsos descubrimientos ha de estar entre "
                               "0 y 1.")
        if gcd(options["block"], sn.CASILLAS) != 1:
            raise CommandError(
                f"El bloque ({options['block']}) tiene que ser coprimo con "
                f"{sn.CASILLAS}: si comparte divisor, los bloques vuelven a caer en "
                f"las mismas casillas y el nulo conserva lo que debe destruir.")

        informes = []
        for symbol in options["symbols"]:
            informe = self._one(symbol.upper(), options)
            informes.append(informe)
            if not options["json"]:
                self._render(informe)

        if options["json"]:
            self.stdout.write(json.dumps(informes, indent=2, ensure_ascii=False,
                                         default=str))

    # ------------------------------------------------------------------

    @staticmethod
    def _one(symbol: str, options: dict) -> dict:
        try:
            from core.application.use_cases.ohlcv_store import load_dataframe
            df = load_dataframe(symbol, options["interval"], options["limit"])
        except Exception:  # noqa: BLE001
            df = None
        if df is None or len(df) < 3:
            return {"symbol": symbol, "interval": options["interval"],
                    "verdict": "SIN_DATOS",
                    "note": (f"No hay velas archivadas de {symbol} en "
                             f"{options['interval']}.")}

        marcas = np.asarray(df["timestamp"].tolist(), dtype=np.int64)
        cierres = np.asarray(df["close"].tolist(), dtype=float)
        cierres = np.where(cierres > 0, cierres, np.nan)
        retornos = np.nan_to_num(np.diff(np.log(cierres)), nan=0.0,
                                 posinf=0.0, neginf=0.0)
        # El retorno `t` se conoce al cerrar la vela `t+1`, así que va con su marca.
        salida = sn.analyse(marcas[1:], retornos, rotations=options["rotations"],
                            fdr=options["fdr"], block=options["block"])
        salida["symbol"] = symbol
        salida["interval"] = options["interval"]
        return salida

    def _render(self, informe: dict) -> None:
        w = self.stdout.write
        w("")
        w(self.style.MIGRATE_HEADING(
            f"{informe.get('symbol', '?')} · {informe.get('interval', '?')} · "
            f"hora de la semana"))

        veredicto = informe.get("verdict", "?")
        estilo = (self.style.SUCCESS if veredicto == "CON_ESTRUCTURA"
                  else self.style.WARNING)
        w(estilo(f"  VEREDICTO: {veredicto}"))
        w(f"  {informe.get('note', '')}")

        if veredicto == "SIN_DATOS":
            return

        g = informe.get("global") or {}
        w("")
        w("  CONTRASTE GLOBAL")
        w(f"    actividad : dispersión p={g.get('p_dispersion_activity', 1):.4f}  "
          f"máximo p={g.get('p_max_activity', 1):.4f}")
        w(f"    dirección : dispersión p={g.get('p_dispersion_return', 1):.4f}  "
          f"máximo p={g.get('p_max_return', 1):.4f}")
        w(f"    umbral {g.get('alpha', 0):.4f} ({g.get('tests', 4)} contrastes) · "
          f"{informe.get('rotations', 0)} réplicas · bloque "
          f"{informe.get('block', 0)}")
        w(f"    {g.get('note', '')}")

        detalle = informe.get("cell_detail")
        if detalle:
            w("")
            w(f"  CASILLAS ({detalle['n_significant']} de {detalle['n_tested']})")
            for c in detalle["significant"][:15]:
                w(f"    {c['day']} {c['hour_utc']:02d}:00 UTC   "
                  f"{c['relative']:.2f}× el movimiento medio   "
                  f"n={c['n']}  z={c['z']:+.1f}  p={c['p']:.2e}")
            w(f"    {detalle['note']}")
            w(f"    {detalle['tail_note']}")

        w("")
        w("  REJILLA (× el movimiento medio; en blanco, sin diferencia)")
        self._grid(informe)

        w("")
        w("  PROTOCOLO")
        w(f"    {informe.get('protocol', '')}")
        w("")
        for linea in sn.self_note().split("\n"):
            w(f"    {linea}")

    def _grid(self, informe: dict) -> None:
        """La rejilla en texto. Solo se marcan las casillas que sobreviven."""
        w = self.stdout.write
        medias = informe.get("mean_abs_return") or []
        if len(medias) != sn.CASILLAS:
            return
        validas = [m for m in medias if m is not None]
        if not validas:
            return
        centro = sum(validas) / len(validas)
        marcadas = {c["cell"] for c in
                    (informe.get("cell_detail") or {}).get("significant", [])}

        w("        " + " ".join(f"{h:>4}" for h in range(0, 24, 2)))
        for d in range(7):
            celdas = []
            for h in range(0, 24, 2):
                c = d * 24 + h
                m = medias[c]
                if m is None or centro <= 0:
                    celdas.append("   ·")
                else:
                    rel = m / centro
                    texto = f"{rel:.1f}"
                    celdas.append(f"{texto:>3}" + ("*" if c in marcadas else " "))
            w(f"    {sn.DAY_NAMES[d]} " + " ".join(celdas))
        w("        (* sobrevive a la corrección por multiplicidad)")
