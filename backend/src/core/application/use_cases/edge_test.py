"""
edge_test.py — ¿Cuál de las dos preguntas tiene señal en MIS datos?

Este módulo no construye nada: decide qué merece la pena construir. Corre las
dos preguntas sobre la misma serie, con la misma validación purgada y el mismo
rigor, y dice cuál de ellas la muestra disponible puede responder.

  · **Dirección** — ¿sube el precio en las próximas N velas? Es la pregunta que
    persigue todo el segmento. En un mercado líquido la autocorrelación de los
    retornos es ≈ 0, así que el efecto a detectar es de 1–2 puntos de precisión,
    y eso necesita del orden de cuatro mil a quince mil observaciones fuera de
    muestra.
  · **Volatilidad** — ¿cuánto se va a mover? El agrupamiento de volatilidad es
    de los hechos más robustos de las finanzas empíricas; el efecto es de otro
    orden de magnitud y se detecta con decenas de observaciones.

La afirmación que hay que falsar, no dar por buena
─────────────────────────────────────────────────
«La volatilidad es predecible» es cierta en la literatura y podría no serlo en
este activo, en este marco temporal y con este histórico. Por eso el criterio no
es que el modelo tenga buen R² —sobre una serie tan persistente, casi cualquier
cosa lo tiene— sino que **supere a la media constante del entrenamiento**, que
es la hipótesis nula literal: si la volatilidad no varía de forma anticipable,
lo mejor que se puede hacer es predecir su nivel medio.

Esa línea base es la que hace honesto el ejercicio. Un R² de 0,45 prediciendo
volatilidad suena magnífico y puede no significar nada.

Una nota sobre el criterio, porque cambió
─────────────────────────────────────────
El planteamiento de partida era «batir a la persistencia». Al calibrar el arnés
sobre series sintéticas con la respuesta conocida, ese criterio falló en las dos
direcciones —detalle completo en `_volatility_question`— y se sustituyó por la
media constante antes de mirar un solo dato real. Se deja escrito porque un
criterio que se ajusta después de ver los resultados es exactamente el defecto
que esta herramienta existe para detectar, y la única defensa es decir cuándo se
cambió y sobre qué datos.

Si la volatilidad no supera a su propio nivel medio en estos datos, la conclusión
no es «hay que probar otro modelo»: es que el reencuadre entero está equivocado
para este activo, y hay que decirlo antes de construir nada encima.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from core.domain.services import significance as sig
from core.domain.services import volatility_forecast as vf
from core.domain.services.purged_cv import PurgedTimeSeriesSplit

logger = logging.getLogger(__name__)

# Ventana de la volatilidad realizada, en velas. Con datos horarios, 24 velas es
# un día: la escala en la que el agrupamiento de volatilidad está documentado.
DEFAULT_RV_WINDOW = 24

# Horizonte de predicción, en velas. Es a la vez el horizonte de la etiqueta y
# el número de velas que hay que purgar — no son dos parámetros, es uno.
DEFAULT_HORIZON = 24


def _direction_question(df: pd.DataFrame, horizon: int, n_splits: int) -> dict:
    """
    ¿Se puede predecir el signo del movimiento? Con el mismo rigor que el resto.

    Usa las features técnicas que el motor ya tiene, para que el resultado sea
    comparable con lo que el producto muestra hoy y no con un modelo distinto.
    """
    from sklearn.ensemble import RandomForestClassifier

    from core.domain.services.technical_analysis_service import _build_prediction_features

    feat = _build_prediction_features(df)
    target = (df["close"].shift(-horizon) > df["close"]).astype(int)
    data = feat.copy()
    data["target"] = target
    data = data.replace([np.inf, -np.inf], np.nan).dropna()
    if len(data) < 150 or data["target"].nunique() < 2:
        return {"answerable": False, "n_oos": 0,
                "note": "Muestra insuficiente para la pregunta direccional."}

    X = data[list(feat.columns)].to_numpy(dtype=float)
    y = data["target"].to_numpy()

    hits = []
    for train_idx, test_idx in PurgedTimeSeriesSplit(n_splits, horizon).split(X):
        if len(set(y[train_idx])) < 2 or len(test_idx) < 10:
            continue
        model = RandomForestClassifier(
            n_estimators=120, max_depth=6, min_samples_leaf=8,
            class_weight="balanced", random_state=42, n_jobs=1,
        ).fit(X[train_idx], y[train_idx])
        hits.append(model.predict(X[test_idx]) == y[test_idx])

    if not hits:
        return {"answerable": False, "n_oos": 0,
                "note": "No hubo tramos utilizables tras purgar."}

    correct = np.concatenate(hits)
    up = float(y.mean())
    baseline = max(up, 1.0 - up)
    stats = sig.edge_significance(int(correct.sum()), correct.size, baseline)

    # Cuánta muestra haría falta para detectar el edge OBSERVADO. Si es mucha más
    # de la que hay, el resultado no dice «no hay edge», dice «no se puede saber».
    needed = vf.observations_needed(vf.accuracy_edge_to_r(stats["edge"])) \
        if stats["edge"] > 0 else None
    return {
        "answerable": bool(needed is not None and needed <= correct.size),
        "n_oos": int(correct.size),
        "accuracy": stats["accuracy"],
        "baseline": stats["baseline"],
        "edge": stats["edge"],
        "edge_ci": [stats["edge_low"], stats["edge_high"]],
        "significant": stats["significant"],
        "observations_needed": needed,
        "note": (
            f"Con {correct.size} observaciones fuera de muestra y un edge observado "
            f"de {stats['edge']:+.1%}, harían falta {needed:,} para detectarlo con "
            "80 % de potencia."
            if needed else
            f"El edge observado no es positivo ({stats['edge']:+.1%}): no hay efecto "
            "cuyo tamaño de muestra calcular."
        ),
    }


# Candidatos a predictor de volatilidad. Son DOS, y el control de multiplicidad
# de más abajo lo asume: declarar predecible «si alguno de los dos funciona» son
# dos oportunidades de acertar por azar, no una.
_VOL_CANDIDATES = ("persistence", "har")


def _volatility_question(df: pd.DataFrame, horizon: int, rv_window: int,
                         n_splits: int) -> dict:
    """
    ¿Se puede predecir cuánto se va a mover? Contra la línea base que importa.

    Se comparan tres predictores sobre las mismas observaciones fuera de muestra:

      · **Media constante del entrenamiento** — la LÍNEA BASE. Representa
        exactamente la hipótesis nula: la volatilidad no varía de forma
        anticipable, así que lo mejor que se puede hacer es predecir su nivel
        medio.
      · **Persistencia** — la volatilidad de las próximas horas será la de las
        últimas. Es un CANDIDATO, no una base (ver abajo).
      · **HAR** — el modelo de referencia de la literatura, tres medias móviles
        sobre escalas distintas. El otro candidato.

    Por qué la persistencia no puede ser la línea base
    ──────────────────────────────────────────────────
    El documento propone «batir a la persistencia» como criterio. Al calibrar el
    arnés sobre series con la respuesta conocida, ese criterio falló **en las dos
    direcciones**, y por el mismo motivo de fondo: la persistencia no es una
    hipótesis nula, es un predictor razonablemente bueno.

    · **Falso positivo.** Sobre una serie homocedástica —volatilidad constante,
      impredecible POR CONSTRUCCIÓN— HAR batía a la persistencia con R² relativo
      +0,45 y p < 0,001, mientras su correlación con lo ocurrido era −0,06. La
      persistencia es un estimador RUIDOSO de una constante, y cualquier
      promedio la mejora encogiendo hacia la media, sin usar información
      temporal.

    · **Falso negativo.** Sobre series GARCH —volatilidad agrupada por
      construcción, con correlación de 0,6–0,7 entre lo predicho y lo ocurrido—
      HAR NO batía a la persistencia de forma significativa en 7 de 9 casos. No
      porque la volatilidad no fuera predecible, sino porque en un GARCH casi
      integrado la persistencia YA ES una predicción casi óptima. Exigir batirla
      es exigir ganar un concurso de modelos, no responder si hay señal.

    La corrección: la hipótesis nula es la MEDIA CONSTANTE
    ─────────────────────────────────────────────────────
    La pregunta es si la volatilidad se puede anticipar, no si HAR es el mejor
    modelo para hacerlo. Así que se prueban los dos candidatos contra la media
    constante y basta con que UNO funcione — si la persistencia sola bate a la
    constante, la volatilidad es predecible y el predictor es la persistencia.

    Dos condiciones por candidato, ambas necesarias:
      1. **Batir a la media constante** (Diebold-Mariano sobre las mismas
         observaciones), que es capturar variación temporal real.
      2. **Correlacionar** con lo que ocurre. Un predictor que acierta el nivel
         pero no el momento no sirve para nada de lo que se construiría encima.

    Y como son dos candidatos, el alfa se reparte entre ellos (Bonferroni): con
    dos oportunidades de acertar por azar, el listón de cada una sube.

    El contraste HAR-vs-persistencia se sigue reportando, pero como lo que es:
    **selección de modelo**, no evidencia de predictibilidad.
    """
    close = df["close"].to_numpy(dtype=float)
    returns = np.concatenate([[0.0], np.diff(np.log(close))])
    rv = vf.realized_volatility(returns, rv_window)
    target = vf.future_volatility(returns, horizon)
    features = vf.har_features(rv)

    ok = np.isfinite(target) & np.isfinite(rv) & np.isfinite(features).all(axis=1)
    if ok.sum() < 150:
        return {"answerable": False, "n_oos": 0, "predictable": False,
                "note": ("Muestra insuficiente para la pregunta de volatilidad "
                         f"({int(ok.sum())} filas utilizables).")}

    X = features[ok]
    y = target[ok]
    persistence = rv[ok]           # «lo mismo que ahora»

    pred_har, actual, pred_persist, base_const = [], [], [], []
    for train_idx, test_idx in PurgedTimeSeriesSplit(n_splits, horizon).split(X):
        if len(train_idx) < 60 or len(test_idx) < 10:
            continue
        model = vf.HARModel().fit(X[train_idx], y[train_idx])
        pred_har.append(model.predict(X[test_idx]))
        actual.append(y[test_idx])
        pred_persist.append(persistence[test_idx])
        # Media del ENTRENAMIENTO, nunca del test: usar la media del tramo que
        # se va a predecir sería regalarle a la base la respuesta, y como la base
        # es la que decide el veredicto, sería fuga a favor de decir que NO.
        base_const.append(np.full(len(test_idx), float(y[train_idx].mean())))

    if not actual:
        return {"answerable": False, "n_oos": 0, "predictable": False,
                "note": "No hubo tramos utilizables tras purgar."}

    actual = np.concatenate(actual)
    base_const = np.concatenate(base_const)
    predictions = {"har": np.concatenate(pred_har),
                   "persistence": np.concatenate(pred_persist)}

    # Bonferroni sobre los dos candidatos: declarar predecible «si alguno de los
    # dos funciona» son dos pruebas, y cobrarlas a 0,05 cada una daría un 10 % de
    # falsos positivos en vez del 5 % anunciado.
    alpha = 0.05 / len(_VOL_CANDIDATES)

    candidates = {}
    for name in _VOL_CANDIDATES:
        pred = predictions[name]
        finite = np.isfinite(actual) & np.isfinite(pred)
        n = int(finite.sum())
        r2 = vf.oos_r2(actual, pred, base_const)
        dm = vf.diebold_mariano(actual - base_const, actual - pred, horizon)
        corr = float(np.corrcoef(actual[finite], pred[finite])[0, 1]) if n > 3 else float("nan")
        # Significancia de la correlación por transformación de Fisher. Se
        # reporta junto al tamaño de efecto porque una correlación de 0,05 sobre
        # tres mil observaciones es distinguible de cero y aun así inútil.
        corr_significant = False
        if np.isfinite(corr) and n > 10:
            from scipy.stats import norm
            z = 0.5 * np.log((1 + corr) / (1 - corr)) * np.sqrt(n - 3)
            corr_significant = bool(z > float(norm.ppf(1 - alpha)))
        beats = bool(dm["p_value"] is not None and dm["p_value"] < alpha)
        candidates[name] = {
            "oos_r2_vs_constant": round(r2, 4) if np.isfinite(r2) else None,
            "dm_vs_constant": dm,
            "beats_constant": beats,
            "correlation": round(corr, 4) if np.isfinite(corr) else None,
            "correlation_significant": corr_significant,
            "works": bool(beats and corr_significant and np.isfinite(corr) and corr > 0),
        }

    working = [n for n in _VOL_CANDIDATES if candidates[n]["works"]]
    predictable = bool(working)
    # El mejor entre los que funcionan, por error cuadrático. Elegir sobre las
    # mismas observaciones con las que se ha contrastado sesga la métrica del
    # elegido al alza; la decisión de SI hay señal ya está tomada arriba y no
    # depende de esta elección, que solo dice cuál usar.
    best = min(working, key=lambda n: float(np.nansum((actual - predictions[n]) ** 2))) \
        if working else None

    # Selección de modelo, no evidencia: ¿aporta HAR algo sobre el predictor
    # trivial? En un GARCH casi integrado la respuesta legítima es «no», y eso no
    # dice nada sobre si la volatilidad es predecible.
    dm_har_vs_persistence = vf.diebold_mariano(
        actual - predictions["persistence"], actual - predictions["har"], horizon)
    r2_har_vs_persistence = vf.oos_r2(actual, predictions["har"], predictions["persistence"])

    corr_best = candidates[best]["correlation"] if best else None
    needed = vf.observations_needed(corr_best) if corr_best and corr_best > 0 else None

    if best:
        detalle = (
            f"El mejor predictor es «{best}»: bate a la media constante "
            f"(R² relativo {candidates[best]['oos_r2_vs_constant']:+.3f}) y "
            f"correlaciona {candidates[best]['correlation']:+.3f} con lo ocurrido.")
    else:
        detalle = ("Ningún candidato bate a la media constante con correlación "
                   "significativa: no hay variación anticipable que capturar.")
    return {
        "answerable": bool(needed is not None and needed <= actual.size),
        "n_oos": int(actual.size),
        "predictable": predictable,
        "best_predictor": best,
        "candidates": candidates,
        "alpha_per_candidate": round(alpha, 4),
        # Atajos al candidato elegido, para que quien lea el informe no tenga que
        # navegar el diccionario de candidatos.
        "correlation": corr_best,
        "correlation_significant": bool(best and candidates[best]["correlation_significant"]),
        "oos_r2_vs_constant": candidates[best]["oos_r2_vs_constant"] if best else None,
        "beats_constant": predictable,
        # Selección de modelo, informativo.
        "har_beats_persistence": bool(dm_har_vs_persistence["better"]),
        "oos_r2_har_vs_persistence": round(r2_har_vs_persistence, 4) if np.isfinite(r2_har_vs_persistence) else None,
        "dm_har_vs_persistence": dm_har_vs_persistence,
        "observations_needed": needed,
        "note": (
            f"Sobre {actual.size} predicciones purgadas, contra la media constante "
            f"del entrenamiento y con alfa repartido entre {len(_VOL_CANDIDATES)} "
            f"candidatos ({alpha:.3f}). {detalle} HAR "
            f"{'bate' if dm_har_vs_persistence['better'] else 'NO bate'} a la "
            "persistencia, que es una cuestión de qué modelo usar y no de si hay "
            "señal."
        ),
    }


def run_edge_test(df: pd.DataFrame, horizon: int = DEFAULT_HORIZON,
                  rv_window: int = DEFAULT_RV_WINDOW, n_splits: int = 5,
                  symbol: str = "", interval: str = "") -> dict:
    """
    Las dos preguntas, la misma serie, la misma validación purgada.

    El veredicto no dice cuál pregunta es «mejor» en abstracto: dice cuál de las
    dos puede responder ESTA muestra. Es la diferencia entre elegir una línea de
    trabajo por convicción y elegirla por potencia estadística.
    """
    direction = _direction_question(df, horizon, n_splits)
    volatility = _volatility_question(df, horizon, rv_window, n_splits)

    if volatility.get("predictable") and not direction.get("significant"):
        verdict = "VOLATILITY"
        conclusion = (
            "La volatilidad es predecible en estos datos por encima de su nivel "
            f"medio (mejor predictor: {volatility.get('best_predictor')}); la "
            "dirección no se distingue del azar. Construir sobre magnitud, no "
            "sobre dirección.")
    elif volatility.get("predictable") and direction.get("significant"):
        verdict = "BOTH"
        conclusion = (
            "Las dos preguntas muestran señal. Conviene revisar la direccional con "
            "más cuidado: es el resultado menos esperable de los dos y el que más "
            "veces resulta ser un artefacto.")
    elif direction.get("significant"):
        verdict = "DIRECTION"
        conclusion = (
            "La dirección muestra señal y la volatilidad no supera a su nivel "
            "medio. Es lo contrario de lo que predice la literatura, así que "
            "antes de construir nada hay que buscar el error.")
    else:
        verdict = "NEITHER"
        conclusion = (
            "Ninguna de las dos preguntas muestra señal con esta muestra. Para la "
            "dirección era lo esperable; para la volatilidad no, y eso invalida el "
            "reencuadre en este activo — hay que decirlo en vez de construir "
            "encima.")

    return {
        "symbol": symbol,
        "interval": interval,
        "candles": int(len(df)),
        "horizon_bars": horizon,
        "rv_window_bars": rv_window,
        "n_splits": n_splits,
        "direction": direction,
        "volatility": volatility,
        "verdict": verdict,
        "conclusion": conclusion,
        "power_reference": {
            "direction_edge_1pct": vf.observations_needed(vf.accuracy_edge_to_r(0.01)),
            "direction_edge_2pct": vf.observations_needed(vf.accuracy_edge_to_r(0.02)),
            "direction_edge_5pct": vf.observations_needed(vf.accuracy_edge_to_r(0.05)),
            "volatility_r030": vf.observations_needed(0.30),
            "volatility_r045": vf.observations_needed(0.45),
            "note": ("Observaciones fuera de muestra necesarias para detectar cada "
                     "efecto con 80 % de potencia. No es una opinión sobre qué "
                     "pregunta es más interesante: es cuál alcanza la muestra."),
        },
        "protocol": (
            "Validación purgada con embargo en las dos preguntas. Para la "
            "volatilidad la hipótesis nula es la MEDIA CONSTANTE del "
            "entrenamiento, no la persistencia: se prueban dos candidatos "
            "—persistencia y HAR— y hace falta que uno bata a esa media Y "
            "correlacione con lo ocurrido, con el alfa repartido entre ambos. "
            "El criterio original del documento —batir a la persistencia— se "
            "descartó al calibrar sobre series con la respuesta conocida, porque "
            "falla en las dos direcciones: una serie homocedástica, impredecible "
            "por construcción, lo cumple con R² relativo +0,45 (cualquier promedio "
            "mejora a un estimador ruidoso de una constante), y series GARCH con "
            "correlación de 0,7 no lo cumplen en 7 de 9 casos (en un GARCH casi "
            "integrado la persistencia ya es casi óptima). Batir a la persistencia "
            "se sigue reportando como selección de modelo, no como evidencia."),
    }


class EdgeTestUseCase:
    """Ejecuta el test sobre el histórico real de un activo."""

    def execute(self, asset_symbol: str, interval: str = "1h",
                limit: int | None = None, horizon: int = DEFAULT_HORIZON,
                rv_window: int = DEFAULT_RV_WINDOW, n_splits: int = 5) -> dict:
        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
        from core.domain.services import generation_power as power

        symbol = asset_symbol.upper()
        if limit is None:
            # El mismo dimensionado por calendario que usa el generador: pedir un
            # recuento fijo de velas da tramos de cinco días en marcos cortos.
            limit = power.recommended_candles(interval)

        result = fetch_ohlcv_dataframe(symbol=symbol, interval=interval, limit=limit)
        if result is None or result.df.empty or len(result.df) < 300:
            available = 0 if result is None or result.df is None else len(result.df)
            return {"error": (f"Se necesitan al menos 300 velas y hay {available} "
                              f"para {symbol} en {interval}."),
                    "candles_available": available}

        report = run_edge_test(result.df, horizon=horizon, rv_window=rv_window,
                              n_splits=n_splits, symbol=symbol, interval=interval)
        report["data_source"] = result.source
        logger.info("edge_test %s/%s → %s", symbol, interval, report["verdict"])
        return report
