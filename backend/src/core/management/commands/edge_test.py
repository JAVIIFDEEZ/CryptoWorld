"""
edge_test — Correr el árbitro sobre datos reales, desde la línea de comandos.

    python manage.py edge_test BTC
    python manage.py edge_test BTC ETH --interval 4h
    python manage.py edge_test BTC --json > btc.json

Por qué un comando y no un endpoint
───────────────────────────────────
Esto no es una función del producto: es un experimento que se corre una vez por
activo y cuyo resultado decide qué se construye después. Colgarlo de la API
invitaría a llamarlo desde la interfaz, y un usuario que ve «VOLATILITY» en una
pantalla lo leerá como una recomendación de operar. No lo es — es una afirmación
sobre qué preguntas puede responder el histórico disponible.

El resultado hay que leerlo con la tabla de potencia al lado. Un `NEITHER` en la
pregunta direccional casi nunca significa «no hay edge»: significa «con esta
muestra no se puede saber», que es una conclusión distinta y mucho menos
interesante. El informe trae ambas cosas por eso.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from core.application.use_cases.edge_test import (
    DEFAULT_HORIZON, DEFAULT_RV_WINDOW, EdgeTestUseCase,
)


class Command(BaseCommand):
    help = ("Mide cuál de las dos preguntas —dirección o volatilidad— tiene señal "
            "en el histórico de un activo, con validación purgada y con embargo.")

    def add_arguments(self, parser):
        parser.add_argument("symbols", nargs="+", help="Símbolos, p. ej. BTC ETH")
        parser.add_argument("--interval", default="1h",
                            help="Marco temporal de las velas (por defecto 1h).")
        parser.add_argument("--horizon", type=int, default=DEFAULT_HORIZON,
                            help=("Velas a predecir. Es TAMBIÉN lo que se purga: "
                                  "no son dos parámetros, es uno."))
        parser.add_argument("--rv-window", type=int, default=DEFAULT_RV_WINDOW,
                            help="Ventana de la volatilidad realizada, en velas.")
        parser.add_argument("--splits", type=int, default=5,
                            help="Tramos de la validación hacia delante.")
        parser.add_argument("--limit", type=int, default=None,
                            help=("Velas a pedir. Por defecto, el dimensionado por "
                                  "calendario del generador."))
        parser.add_argument("--json", action="store_true",
                            help="Volcar el informe completo en JSON.")

    def handle(self, *args, **options):
        if options["horizon"] < 1 or options["rv_window"] < 1:
            raise CommandError("El horizonte y la ventana han de ser positivos.")

        use_case = EdgeTestUseCase()
        informes = []
        for symbol in options["symbols"]:
            report = use_case.execute(
                symbol, interval=options["interval"], limit=options["limit"],
                horizon=options["horizon"], rv_window=options["rv_window"],
                n_splits=options["splits"],
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
        symbol = report.get("symbol", "?")
        if "error" in report:
            w(self.style.ERROR(f"{symbol}: {report['error']}"))
            return

        w("")
        w(self.style.MIGRATE_HEADING(
            f"{symbol} · {report['interval']} · {report['candles']} velas "
            f"· fuente {report.get('data_source', '?')}"))

        verdict = report["verdict"]
        estilo = self.style.SUCCESS if verdict in ("VOLATILITY", "BOTH") else self.style.WARNING
        w(estilo(f"  VEREDICTO: {verdict}"))
        w(f"  {report['conclusion']}")

        d = report["direction"]
        w("")
        w("  DIRECCIÓN")
        if d.get("n_oos"):
            w(f"    {d['n_oos']} observaciones fuera de muestra · "
              f"precisión {d.get('accuracy')} sobre base {d.get('baseline')}")
            w(f"    edge {d.get('edge')} · IC95 {d.get('edge_ci')} · "
              f"significativo: {d.get('significant')}")
        w(f"    {d.get('note', '')}")

        v = report["volatility"]
        w("")
        w("  VOLATILIDAD")
        if v.get("n_oos"):
            w(f"    {v['n_oos']} predicciones purgadas · "
              f"predecible: {v.get('predictable')} · "
              f"mejor predictor: {v.get('best_predictor')}")
            for name, c in (v.get("candidates") or {}).items():
                w(f"      {name:12s} R² vs media constante {c['oos_r2_vs_constant']} · "
                  f"la bate: {c['beats_constant']} · corr {c['correlation']} "
                  f"(significativa: {c['correlation_significant']})")
            w(f"      HAR bate a la persistencia: {v.get('har_beats_persistence')} "
              f"— selección de modelo, no evidencia de señal")
        w(f"    {v.get('note', '')}")

        ref = report["power_reference"]
        w("")
        w("  CUÁNTA MUESTRA HARÍA FALTA (80 % de potencia)")
        w(f"    dirección, edge 1 % ....... {ref['direction_edge_1pct']:>7,}")
        w(f"    dirección, edge 2 % ....... {ref['direction_edge_2pct']:>7,}")
        w(f"    volatilidad, r = 0,30 ..... {ref['volatility_r030']:>7,}")
        w(f"    volatilidad, r = 0,45 ..... {ref['volatility_r045']:>7,}")
        w("")
        w("  PROTOCOLO")
        w(f"    {report['protocol']}")
        w("")
