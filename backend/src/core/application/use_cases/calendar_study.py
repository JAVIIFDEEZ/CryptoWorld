"""
calendar_study.py — Qué eventos mueven de verdad a un activo, sobre datos propios.

Junta las dos piezas: el calendario derivable por regla y el estudio de eventos
con su grupo de control. Corre entero sobre el almacén propio de velas, así que
no pide nada a ningún exchange y funciona con la red caída.

Para qué sirve el resultado
──────────────────────────
Para dos cosas distintas, y conviene no confundirlas:

1. **Decidir qué variables de calendario merecen entrar al modelo.** Una familia
   que no mueve nada es una columna que solo añade ruido y dimensión, y el
   estudio de importancia repartiría crédito entre ella y sus vecinas. Este
   informe es el filtro previo.
2. **Saber cuándo NO operar.** Es el uso más inmediato y el menos vistoso: si la
   volatilidad se multiplica por dos en la ventana de un evento, ese es el peor
   momento para que un stop se ejecute por deslizamiento, y saberlo vale más que
   cualquier intento de anticipar la dirección.

Lo que este caso de uso añade sobre el dominio
─────────────────────────────────────────────
· **Los ajustes de cada familia no se eligen aquí.** Vienen declarados en
  `economic_calendar.FAMILY_STUDY_HINTS`, porque el modo de control correcto es
  una propiedad de la estructura temporal de la familia y no una preferencia:
  para las liquidaciones de financiación hay que acortar la ventana y desplazar
  el control, y para el vencimiento mensual hay que compararlo con los demás
  viernes. Equivocarlo produce un estudio que corre y no significa nada.
· **La multiplicidad se corrige.** Ocho familias por dos preguntas son dieciséis
  contrastes; quedarse con el que salió pequeño es el defecto clásico. Se aplica
  Benjamini-Hochberg sobre todos los p-valores del informe y se dice cuáles
  sobreviven.
· **La potencia viaja con cada familia.** Cuatro halvings no permiten concluir
  nada, y el informe lo dice en vez de devolver un «sin efecto» que se leería
  como un hallazgo.
"""

from __future__ import annotations

import logging

import numpy as np

from core.domain.services import economic_calendar as cal
from core.domain.services import event_study as es

logger = logging.getLogger(__name__)

# Velas por defecto. Tres años de horarias dan 36 nóminas y 36 vencimientos
# mensuales: el mínimo con el que las familias mensuales tienen algo de potencia.
DEFAULT_LIMIT = 26_000

# Tasa de falsos descubrimientos con la que se corrige la multiplicidad.
DEFAULT_FDR = 0.10


class CalendarStudyUseCase:
    """¿Qué eventos programados mueven a este activo, y cuáles no se pueden saber?"""

    def execute(self, asset_symbol: str, interval: str = "1h",
                limit: int = DEFAULT_LIMIT,
                families: tuple[str, ...] | None = None,
                replicates: int = es.DEFAULT_REPLICATES,
                fdr: float = DEFAULT_FDR) -> dict:
        symbol = asset_symbol.upper()
        marcas, retornos = self._load(symbol, interval, limit)
        if marcas is None:
            return {
                "symbol": symbol, "interval": interval, "verdict": "SIN_DATOS",
                "families": [],
                "note": (f"No hay velas archivadas de {symbol} en {interval}. El "
                         f"estudio corre sobre el almacén propio, así que primero "
                         f"hay que ingerir histórico."),
            }

        eventos = cal.derived_calendar(int(marcas[0]), int(marcas[-1]), families)
        resumen = cal.describe(eventos)

        por_familia: dict[str, list] = {}
        for e in eventos:
            por_familia.setdefault(e.key, []).append(e.scheduled_at)

        informes = []
        for clave in sorted(por_familia):
            pista = cal.study_hint(clave)
            salida = es.study(
                marcas, retornos,
                np.array(por_familia[clave], dtype=np.int64),
                post=int(pista.get("post", es.DEFAULT_POST)),
                null_mode=pista.get("null_mode", "matched"),
                offset_hours=float(pista.get("offset_hours", 4.0)),
                replicates=replicates,
                # La semilla sale del nombre de la familia y no de `hash()`, que va
                # salado por proceso: si no, dos ejecuciones sobre los mismos datos
                # darían p-valores distintos y el informe no sería reproducible.
                seed=self._seed(symbol, clave),
            )
            salida["family"] = clave
            salida["hint"] = pista
            informes.append(salida)

        self._correct_multiplicity(informes, fdr)

        con_efecto = [i for i in informes if i.get("survives_fdr")]
        informe = {
            "symbol": symbol,
            "interval": interval,
            "candles": int(marcas.size),
            "first": self._iso(marcas[0]),
            "last": self._iso(marcas[-1]),
            "calendar": resumen,
            "families": sorted(informes, key=lambda i: (
                not i.get("survives_fdr"), i.get("p_volatility") or 1.0)),
            "families_studied": len(informes),
            "families_with_effect": len(con_efecto),
            "fdr": fdr,
            "protocol": (
                "Cada familia se estudia con el modo de control que su estructura "
                "temporal exige, declarado en el propio calendario y no elegido "
                "aquí. El contraste es una permutación de etiquetas entre eventos y "
                "controles, y los p-valores de todas las familias pasan por "
                "Benjamini-Hochberg antes de llamar efecto a ninguno."),
        }
        informe["verdict"] = ("SIN_DATOS" if not informes else
                              "CON_EFECTOS" if con_efecto else "SIN_EFECTOS")
        informe["note"] = self._note(informe)
        logger.info("calendar_study %s %s → %s (%d/%d familias con efecto)",
                    symbol, interval, informe["verdict"], len(con_efecto),
                    len(informes))
        return informe

    # ------------------------------------------------------------------ carga

    @staticmethod
    def _load(symbol: str, interval: str, limit: int):
        try:
            from core.application.use_cases.ohlcv_store import load_dataframe
            df = load_dataframe(symbol, interval, limit)
        except Exception:  # noqa: BLE001 — sin almacén el estudio lo dice
            logger.info("calendar_study: almacén no disponible para %s", symbol)
            return None, None
        if df is None or len(df) < 300:
            return None, None

        marcas = np.asarray(df["timestamp"].tolist(), dtype=np.int64)
        cierres = np.asarray(df["close"].tolist(), dtype=float)
        cierres = np.where(cierres > 0, cierres, np.nan)
        retornos = np.nan_to_num(np.diff(np.log(cierres)), nan=0.0,
                                 posinf=0.0, neginf=0.0)
        # El retorno `t` nace de las velas `t` y `t+1`, así que va con la marca de
        # la SEGUNDA: es cuando se conoce. Alinearlo con la primera adelantaría
        # todo el estudio una vela.
        return marcas[1:], retornos

    @staticmethod
    def _seed(symbol: str, family: str) -> int:
        from zlib import crc32
        return crc32(f"{symbol}:{family}".encode()) & 0x7FFFFFFF

    @staticmethod
    def _iso(ms) -> str:
        from datetime import datetime, timezone as _tz
        return datetime.fromtimestamp(int(ms) / 1000, _tz.utc).isoformat()

    # ------------------------------------------------------- multiplicidad

    @staticmethod
    def _correct_multiplicity(informes: list[dict], fdr: float) -> None:
        """Benjamini-Hochberg sobre TODOS los p-valores del informe.

        Ocho familias por dos preguntas son dieciséis contrastes. Sin corrección,
        con cero efecto real se espera casi un positivo por informe solo por azar,
        y el informe lo presentaría como un hallazgo. Se anota en cada familia si
        sobrevive, sin borrar el p-valor original: un número corregido a
        escondidas es peor que uno crudo con su contexto.
        """
        from core.domain.services import significance as sig

        entradas = []
        for i, inf in enumerate(informes):
            for pregunta in ("p_volatility", "p_direction"):
                p = inf.get(pregunta)
                if p is not None and np.isfinite(p):
                    entradas.append((i, pregunta, float(p)))

        if not entradas:
            for inf in informes:
                inf["survives_fdr"] = False
            return

        salida = sig.benjamini_hochberg([e[2] for e in entradas], fdr=fdr)
        sobrevive: dict[int, set] = {}
        for pos, (i, pregunta, _) in enumerate(entradas):
            if salida["results"][pos]["significant"]:
                sobrevive.setdefault(i, set()).add(pregunta)

        for i, inf in enumerate(informes):
            preguntas = sobrevive.get(i, set())
            inf["survives_fdr"] = bool(preguntas)
            inf["survives_questions"] = sorted(preguntas)
            inf["fdr_threshold"] = salida.get("threshold")
            inf["fdr_tests"] = len(entradas)

    @staticmethod
    def _note(informe: dict) -> str:
        n = informe["families_studied"]
        con = informe["families_with_effect"]
        if not n:
            return "No había ninguna familia de eventos con datos suficientes."
        sin_potencia = sum(1 for f in informe["families"]
                           if f.get("verdict") in ("SIN_POTENCIA", "NO_IDENTIFICABLE"))
        base = (f"{n} familias estudiadas, {con} con efecto que sobrevive a la "
                f"corrección por multiplicidad. ")
        if sin_potencia:
            base += (f"{sin_potencia} no admiten conclusión —muy pocos eventos o "
                     f"efecto no separable del de su hora— y eso NO es «sin "
                     f"efecto». ")
        if not con:
            return base + ("Ninguna familia mueve este activo de forma detectable "
                           "con el histórico disponible.")
        return base + ("Las familias con efecto son candidatas a entrar como "
                       "variable del modelo y, sobre todo, a marcar ventanas en las "
                       "que no conviene ejecutar.")
