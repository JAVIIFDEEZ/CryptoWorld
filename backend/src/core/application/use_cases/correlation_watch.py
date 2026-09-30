"""
correlation_watch.py — Vigilar si la diversificación sigue existiendo.

Una cartera de cripto se justifica con un número que casi nadie vuelve a mirar
después de construirla: la correlación entre sus patas. Y es justo el número que
se mueve. En los episodios que importan —marzo de 2020, mayo de 2021, el colapso
de Terra, el de FTX— las correlaciones entre activos de este mercado se van
hacia uno, y la cartera que parecía repartida en cinco riesgos resulta ser una
posición apalancada en uno solo. El daño no llega cuando cambia la correlación:
llega cuando alguien se entera tres meses después.

Esto lo vigila en continuo sobre el histórico ya archivado. No pide nada a
ningún exchange, así que corre aunque la red esté caída y no consume cuota.

Lo que este caso de uso aporta sobre el detector de dominio
──────────────────────────────────────────────────────────
El detector es aritmética sobre dos vectores. Aquí está lo que puede
equivocarse con datos de verdad, y que ningún test de dominio detectaría:

1. **La alineación por marca temporal.** `load_dataframe` devuelve las últimas N
   velas de CADA símbolo por separado. Si a uno le falta una vela —y faltan: hay
   un `find_gaps` en este mismo almacén porque faltan— las dos series quedan
   desfasadas una posición y la correlación medida deja de ser la correlación.
   Un desfase de una barra sobre datos horarios puede convertir un 0,85 en un
   0,2. Así que las series se UNEN por `open_time`, no se emparejan por posición,
   y el informe declara cuántas velas sobrevivieron a la unión.
2. **Volver a fechar los índices.** El detector habla en índices de su serie
   interna, que ha pasado por el cebado de la volatilidad, por la ventana móvil
   y por el corte de referencia. Un índice sin fecha no sirve para decidir nada;
   aquí se traduce a la marca temporal de la vela.
3. **Las parejas.** Con n activos hay n(n−1)/2 parejas y cada una es un contraste.
   Mirar quince y quedarse con la que saltó es el defecto clásico. El informe
   dice cuántas se miraron y cuántas se esperaba que saltaran por azar, y con
   `family_wise` reparte el α entre todas para que el 5 % sea la probabilidad de
   una falsa alarma en la cartera COMPLETA. No es el comportamiento por defecto
   porque cuesta potencia: con quince parejas cada una se juzgaría al 0,33 % y
   las caídas moderadas dejarían de verse. La elección viaja en la salida.
"""

from __future__ import annotations

import itertools
import logging

import numpy as np

from core.domain.services import structural_break as sb

logger = logging.getLogger(__name__)

# Velas que se piden por símbolo. Con 4.000 horarias hay medio año largo, que da
# de sobra para una referencia de 12 ventanas independientes y un tramo vigilado
# que merezca el nombre.
DEFAULT_LIMIT = 4000

# Fracción del histórico que hace de tramo tranquilo. 0,5 reparte el error entre
# las dos cosas que dependen de él: una referencia corta da una sigma ruidosa y
# un tramo vigilado corto no da tiempo a que la ruptura se acumule.
DEFAULT_REFERENCE_FRAC = 0.5


class CorrelationWatchUseCase:
    """¿Sigue siendo cierta la correlación con la que se construyó la cartera?"""

    def execute(self, symbols: list[str], interval: str = "1h",
                limit: int = DEFAULT_LIMIT,
                window: int = sb.DEFAULT_CORR_WINDOW,
                detect_drop: float = sb.DEFAULT_DETECT_DROP,
                alpha: float = sb.DEFAULT_ALPHA,
                reference_frac: float = DEFAULT_REFERENCE_FRAC,
                replicates: int = sb.DEFAULT_REPLICATES,
                family_wise: bool = False) -> dict:
        # Mayúsculas ANTES de quitar duplicados: al revés, «btc» y «BTC» pasaban
        # el filtro de dos activos siendo uno solo.
        simbolos = list(dict.fromkeys(s.upper() for s in symbols))
        if len(simbolos) < 2:
            return {"verdict": "SIN_DATOS", "pairs": [],
                    "note": "Hacen falta al menos dos activos para una correlación."}

        series, ausentes = self._load_aligned(simbolos, interval, limit)
        if series is None or len(series["symbols"]) < 2:
            return {"verdict": "SIN_DATOS", "pairs": [], "missing": ausentes,
                    "interval": interval,
                    "note": (f"No hay dos activos con histórico alineado en el "
                             f"almacén para {interval}. Faltan: "
                             f"{', '.join(ausentes) or 'ninguno'}.")}

        marcas = series["open_time"]
        disponibles = series["symbols"]
        combinaciones = list(itertools.combinations(disponibles, 2))

        # Con n activos hay n(n−1)/2 contrastes. `family_wise` reparte el α entre
        # todos (Bonferroni), de modo que el 5 % pasa a ser la probabilidad de UNA
        # falsa alarma en TODA la cartera y no en cada pareja. Cuesta potencia y por
        # eso no es el defecto: con quince parejas, cada una se juzga al 0,33 % y
        # las rupturas pequeñas dejan de verse. Se elige, y queda declarado.
        alpha_pareja = (alpha / len(combinaciones)
                        if family_wise and combinaciones else alpha)

        parejas = []
        for a, b in combinaciones:
            ra = self._log_returns(series["close"][a])
            rb = self._log_returns(series["close"][b])
            n_ref = self._reference_length(ra.size, window, reference_frac)
            salida = sb.correlation_break(
                ra, rb, window=window, reference=n_ref, detect_drop=detect_drop,
                alpha=alpha_pareja, replicates=replicates, seed=self._seed(a, b),
            )
            salida["pair"] = f"{a}/{b}"
            self._stamp(salida, marcas, window)
            parejas.append(salida)

        rotas = [p for p in parejas if p.get("broken")]
        evaluadas = [p for p in parejas if p.get("verdict") in ("ROTO", "ESTABLE")]
        esperadas = alpha_pareja * len(evaluadas)

        informe = {
            "interval": interval,
            "symbols": disponibles,
            "missing": ausentes,
            "candles_aligned": int(marcas.size),
            "first": self._iso(marcas[0]) if marcas.size else None,
            "last": self._iso(marcas[-1]) if marcas.size else None,
            "window": window,
            "detect_drop": detect_drop,
            "alpha": alpha,
            "alpha_per_pair": alpha_pareja,
            "family_wise": bool(family_wise),
            "pairs_evaluated": len(evaluadas),
            "pairs_broken": len(rotas),
            "expected_by_chance": round(esperadas, 2),
            "pairs": sorted(parejas, key=lambda p: (not p.get("broken"),
                                                    -(p.get("peak") or 0.0))),
            "protocol": (
                "Correlación de cada pareja sobre retornos logarítmicos UNIDOS por "
                "marca temporal, desvolatilizados, con CUSUM de dos colas sobre la "
                "z de Fisher. El umbral de cada pareja se calibra contra su propio "
                "nulo de correlación constante."),
        }
        informe["chance_of_this_many"] = round(
            self._binomial_tail(len(rotas), len(evaluadas), alpha_pareja), 4)
        informe["verdict"] = self._verdict(evaluadas, rotas, alpha_pareja)
        informe["note"] = self._note(informe)
        logger.info("correlation_watch %s → %s (%d/%d rotas)", interval,
                    informe["verdict"], len(rotas), len(evaluadas))
        return informe

    # ------------------------------------------------------------------ carga

    @staticmethod
    def _load_aligned(simbolos: list[str], interval: str, limit: int):
        """Velas de todos los símbolos UNIDAS por `open_time`.

        La intersección de marcas temporales, no la posición. Un símbolo al que
        le falte una vela desfasaría todo lo que viene detrás, y una correlación
        sobre series desfasadas una barra no es una correlación mal estimada:
        es otra cantidad.
        """
        try:
            from core.application.use_cases.ohlcv_store import load_dataframe
        except Exception:  # noqa: BLE001
            return None, list(simbolos)

        cierres: dict[str, dict[int, float]] = {}
        ausentes: list[str] = []
        for s in simbolos:
            try:
                df = load_dataframe(s, interval, limit)
            except Exception:  # noqa: BLE001
                logger.info("correlation_watch: sin almacén para %s", s)
                ausentes.append(s)
                continue
            if df is None or len(df) < 2:
                ausentes.append(s)
                continue
            cierres[s] = dict(zip(df["timestamp"].tolist(), df["close"].tolist()))

        if len(cierres) < 2:
            return None, ausentes

        comunes = set.intersection(*(set(v) for v in cierres.values()))
        marcas = np.array(sorted(comunes), dtype=np.int64)
        if marcas.size < 2:
            return None, ausentes

        return ({"open_time": marcas,
                 "symbols": sorted(cierres),
                 "close": {s: np.array([cierres[s][t] for t in marcas], dtype=float)
                           for s in cierres}},
                ausentes)

    @staticmethod
    def _seed(a: str, b: str) -> int:
        """Semilla ESTABLE derivada del nombre de la pareja.

        No se usa `hash()`. El hash de una cadena en Python va salado por proceso
        —`PYTHONHASHSEED` es aleatorio por defecto—, así que la misma pareja sobre
        los mismos datos habría calibrado un umbral distinto en cada ejecución.
        Sobre un informe que puede decidir si se recorta una posición, eso no es
        una imprecisión: es que el resultado no se puede reproducir ni auditar, y
        dos ejecuciones seguidas podrían dar veredictos opuestos sin que nada
        hubiera cambiado en el mercado.
        """
        from zlib import crc32
        return crc32(f"{a}/{b}".encode()) & 0x7FFFFFFF

    @staticmethod
    def _log_returns(close: np.ndarray) -> np.ndarray:
        c = np.asarray(close, dtype=float)
        c = np.where(c > 0, c, np.nan)
        r = np.diff(np.log(c))
        return np.nan_to_num(r, nan=0.0, posinf=0.0, neginf=0.0)

    @staticmethod
    def _reference_length(n_returns: int, window: int, frac: float) -> int:
        """Longitud del tramo tranquilo, en observaciones de la correlación."""
        n_corr = max(n_returns - sb.DEVOL_WARMUP - window + 1, 0)
        return max(int(n_corr * min(max(frac, 0.1), 0.9)), 0)

    # ------------------------------------------------------------- fechado

    @staticmethod
    def _stamp(salida: dict, marcas: np.ndarray, window: int) -> None:
        """Traduce los índices internos del detector a marcas temporales.

        Tres desplazamientos encadenados, y cada uno se ha equivocado una vez al
        escribirlo:
          · el retorno `t` nace de las velas `t` y `t+1`, así que va con `t+1`;
          · el cebado de la volatilidad local se come los primeros retornos;
          · la correlación del índice `j` resume los retornos [j, j+w), así que su
            ventana ACABA en el retorno `j+w−1`.
        """
        if not salida.get("broken"):
            return
        ref = int(salida.get("reference", 0))
        cebado = int(salida.get("warmup_returns_dropped", 0))
        w = int(window)

        def vela_final(indice_vigilado: int) -> int:
            # índice de vela donde ACABA la ventana de esa observación
            return indice_vigilado + ref + cebado + w

        def vela_inicial(indice_vigilado: int) -> int:
            return indice_vigilado + ref + cebado + 1

        def iso(i: int):
            if 0 <= i < marcas.size:
                from datetime import datetime, timezone as _tz
                return datetime.fromtimestamp(int(marcas[i]) / 1000, _tz.utc).isoformat()
            return None

        salida["alarm_time"] = iso(vela_final(int(salida["alarm_index"])))
        # Del punto de cambio interesa el PRINCIPIO de su ventana: es la vela más
        # antigua que puede estar implicada en el cambio estimado.
        salida["change_point_time"] = iso(vela_inicial(int(salida["change_point_index"])))

    @staticmethod
    def _iso(ms) -> str:
        from datetime import datetime, timezone as _tz
        return datetime.fromtimestamp(int(ms) / 1000, _tz.utc).isoformat()

    # ------------------------------------------------------------ veredicto

    @staticmethod
    def _binomial_tail(k: int, n: int, p: float) -> float:
        """P(X ≥ k) con X ~ Binomial(n, p). Sin dependencias."""
        from math import comb
        if k <= 0:
            return 1.0
        if n <= 0 or p <= 0:
            return 0.0
        p = min(p, 1.0)
        return float(sum(comb(n, i) * p ** i * (1 - p) ** (n - i)
                         for i in range(k, n + 1)))

    @classmethod
    def _verdict(cls, evaluadas: list, rotas: list, alpha_pareja: float) -> str:
        """Veredicto agregado contra la cola binomial, no contra la media.

        La versión anterior comparaba el número de roturas con el número esperado
        por azar, y con seis parejas al 5 % una sola rotura (esperadas 0,3) salía
        ROTO. Pero UNA rotura entre seis contrastes independientes al 5 % ocurre el
        26 % de las veces sin que nada haya cambiado: llamar a eso ROTO es
        exactamente el error de las pruebas múltiples que el informe dice vigilar.

        Así que se pregunta lo correcto: ¿cuál es la probabilidad de ver AL MENOS
        estas roturas si ninguna fuera real? Con `family_wise` activo el α por
        pareja ya está repartido, así que una sola rotura sí cruza el umbral — que
        es justo para lo que sirve ese reparto.
        """
        if not evaluadas:
            return "SIN_DATOS"
        if not rotas:
            return "ESTABLE"
        p = cls._binomial_tail(len(rotas), len(evaluadas), alpha_pareja)
        return "ROTO" if p < 0.05 else "INDICIOS"

    @staticmethod
    def _note(informe: dict) -> str:
        n = informe["pairs_evaluated"]
        rotas = informe["pairs_broken"]
        esp = informe["expected_by_chance"]
        if informe["verdict"] == "SIN_DATOS":
            return "Ninguna pareja tenía histórico suficiente para un veredicto."
        reparto = (f"α={informe['alpha']:.0%} repartido entre las parejas "
                   f"({informe['alpha_per_pair']:.2%} cada una)"
                   if informe.get("family_wise")
                   else f"α={informe['alpha']:.0%} por pareja")
        base = (f"{rotas} de {n} parejas con ruptura, y por azar se esperaban "
                f"{esp:.1f} con {reparto}. ")
        if informe["verdict"] == "ESTABLE":
            return base + ("Ninguna evidencia de que la diversificación haya "
                           "cambiado. No es lo mismo que evidencia de que aguante.")
        azar = informe.get("chance_of_this_many")
        cola = (f"Ver al menos {rotas} sin que ninguna sea real tiene una "
                f"probabilidad del {azar:.1%}. " if azar is not None else "")
        if informe["verdict"] == "INDICIOS":
            return base + cola + ("No basta para afirmar nada de la cartera: hay "
                                  "que mirar la pareja concreta antes de mover nada.")
        return base + cola + ("Más rupturas de las que explica el azar: la cartera "
                              "ya no reparte el riesgo como cuando se construyó.")
