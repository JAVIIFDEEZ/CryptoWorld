"""
meta_sizing.py — El meta-modelo entra en el generador: de señal a tamaño.

`labeling.py` etiqueta, `meta_model.py` aprende y `backtest_execution.py` sabe
dimensionar por convicción. Faltaba la pieza que une las tres con un spec real:
esto. Sin ella el modo `conviction` existía en el motor pero ningún preset lo
usaba — código correcto y muerto.

Qué hace exactamente
────────────────────
El spec compilado decide **dónde** entrar. Sobre esas mismas entradas se
construye el problema del meta-modelo: cada señal se etiqueta con la triple
barrera (¿objetivo, stop o tiempo?), se entrena un clasificador que aprende
**cuándo esa señal acierta** y su probabilidad se traduce en fracción de capital.
Por debajo del suelo de convicción, el tamaño es cero: la señal se deja pasar.

Tres decisiones de rigor, y por qué
───────────────────────────────────
· **El mapa de convicción se indexa por la vela de RELLENO, no por la de la
  señal.** El motor ejecuta la orden en la apertura de `s+1`, y es ahí donde
  consulta el tamaño. Las features, en cambio, se leen en `s` — la vela cuyo
  cierre originó la señal. Indexar ambas cosas igual sería decidir el tamaño
  con el cierre de la vela en cuya apertura se opera: una fuga silenciosa, del
  tipo que el detector de lookahead no ve porque las señales sí son causales.

· **Los eventos son TODAS las velas con señal, no solo los trades ejecutados.**
  Restringirse a lo que el backtest pudo tomar (estaba plano) encoge la muestra
  y la sesga hacia los tramos de baja densidad de señal. Que las etiquetas se
  solapen no es un problema: para eso están los pesos por unicidad.

· **La medición es fuera de muestra.** El overlay se evalúa en el tramo que el
  meta-modelo no vio al entrenar, comparando el mismo spec con y sin convicción.
  Entrenar y medir sobre todo el histórico daría siempre mejora, y sería falsa.

Y una que no es de rigor sino de honestidad: si el meta-modelo no supera al
primario, se dice y no se aplica. Filtrar con ruido es peor que no filtrar.

Capa de dominio: NumPy/pandas + scikit-learn (vía meta_model), sin Django.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from core.domain.services import backtest_metrics as metrics
from core.domain.services import labeling, meta_model
from core.domain.services.backtest_execution import CostModel, SizingModel
from core.domain.services.strategy_spec import compile_signals, spec_risk, spec_sizing
from core.domain.services.technical_analysis_service import backtest_signals


@dataclass(frozen=True)
class ConvictionConfig:
    """Presupuesto y geometría del overlay de convicción."""
    barriers: labeling.BarrierConfig = field(default_factory=labeling.BarrierConfig)
    meta: meta_model.MetaModelConfig = field(default_factory=meta_model.MetaModelConfig)
    min_events: int = 60          # por debajo, no hay con qué entrenar nada creíble
    floor: float = 0.5            # convicción mínima para operar (bet_size)
    max_fraction: float = 1.0     # tope de capital por operación
    fallback_fraction: float = 1.0  # tamaño de las señales sin convicción medible


def market_features(df):
    """
    Estado de mercado en cada vela, con lo conocido AL CIERRE de esa vela.

    Deliberadamente genéricas y pocas: el meta-modelo no debe replicar la señal
    del primario (eso ya está decidido) sino describir el contexto en que esa
    señal se emite. Más features sobre unos cientos de eventos es más superficie
    de sobreajuste, no más información.
    """
    import pandas as pd

    close = df["close"].astype(float)
    high = df["high"].astype(float) if "high" in df else close
    low = df["low"].astype(float) if "low" in df else close
    volume = df["volume"].astype(float) if "volume" in df else pd.Series(
        np.ones(len(df)), index=df.index)

    ret = close.pct_change()
    vol20 = pd.Series(labeling.realized_volatility(close.to_numpy(), 20), index=df.index)
    vol60 = pd.Series(labeling.realized_volatility(close.to_numpy(), 60), index=df.index)
    sma50 = close.rolling(50, min_periods=50).mean()
    roll_max = close.rolling(60, min_periods=60).max()
    vol_mean = volume.rolling(20, min_periods=20).mean()

    out = pd.DataFrame({
        "ret_1": ret,
        "ret_5": close.pct_change(5),
        "ret_20": close.pct_change(20),
        "vol_20": vol20,
        # Régimen de volatilidad: la corta contra la larga. Un mismo retorno
        # significa cosas distintas según si la calma se está rompiendo o no.
        "vol_regime": vol20 / vol60.replace(0.0, np.nan),
        "dist_sma50": (close - sma50) / sma50.replace(0.0, np.nan),
        "drawdown_60": close / roll_max.replace(0.0, np.nan) - 1.0,
        "range_pct": (high - low) / close.replace(0.0, np.nan),
        "volume_ratio": volume / vol_mean.replace(0.0, np.nan),
    })
    return out.replace([np.inf, -np.inf], np.nan)


def _signal_bars(signals) -> list[int]:
    """Velas en las que el primario propone entrada."""
    return [int(i) for i in np.flatnonzero(np.asarray(signals) == 1)]


def conviction_sizing(sizes: dict[int, float], base_fraction: float = 1.0,
                      offset: int = 0) -> SizingModel:
    """
    Traduce {vela de señal → fracción} al `SizingModel` que el motor entiende.

    El desplazamiento `+1` es la traducción de la convención de ejecución: la
    señal de `s` se rellena en la apertura de `s+1`, y `_position_notional`
    consulta el tamaño con el índice de la vela en que rellena. `offset` reindexa
    a un tramo del histórico (los backtests por segmento reciben un DataFrame que
    empieza en 0).
    """
    pairs = tuple(sorted(
        (int(s) + 1 - offset, float(size)) for s, size in sizes.items()
        if int(s) + 1 - offset >= 0
    ))
    return SizingModel(mode="conviction", fraction=float(base_fraction), conviction=pairs)


def _base_fraction(spec: dict) -> float:
    """Tamaño al que se repliega una señal sin convicción medible."""
    sizing = spec.get("sizing")
    if sizing and sizing.get("mode") == "fraction":
        return float(sizing.get("fraction", 1.0))
    return 1.0


def _summarize(model: dict) -> dict:
    """Lo publicable del meta-modelo (el estimador entrenado no viaja en JSON)."""
    return {k: v for k, v in model.items() if k not in ("model", "feature_names")}


def conviction_overlay(df, spec: dict, ppy: float = 365.0,
                       costs: CostModel | None = None,
                       config: ConvictionConfig | None = None) -> dict:
    """
    Entrena el meta-modelo del spec y mide, FUERA DE MUESTRA, qué aporta
    dimensionar por convicción frente a operar todas las señales igual.

    Devuelve siempre un veredicto legible: o el meta-modelo aporta y se cuantifica
    cuánto, o no aporta y se dice por qué. Nunca aplica un tamaño modulado sin
    haber demostrado antes que la modulación tiene fundamento.
    """
    cfg = config or ConvictionConfig()

    signals = compile_signals(df, spec)
    events = _signal_bars(signals)
    if len(events) < cfg.min_events:
        return {
            "applied": False,
            "reason": "insufficient_events",
            "n_events": len(events),
            "note": (f"Solo {len(events)} velas con señal: por debajo de "
                     f"{cfg.min_events} no hay muestra para entrenar un "
                     "meta-modelo sin sobreajustarlo."),
        }

    features = market_features(df)
    labels = labeling.triple_barrier_labels(df, events, cfg.barriers)
    if labels.get("n_events", 0) == 0:
        return {"applied": False, "reason": "unlabelable",
                "note": labels.get("note", "No se pudo etiquetar con triple barrera.")}

    trained = meta_model.train_meta_model(features, labels["labels"], config=cfg.meta)
    if not trained.get("usable"):
        return {
            "applied": False,
            "reason": "no_edge",
            "meta_model": _summarize(trained),
            "labels": {"n_events": labels["n_events"], "counts": labels.get("counts")},
            "note": trained.get("note", "El meta-modelo no aporta sobre el primario."),
        }

    # ── Traducción económica, medida donde el modelo no entrenó ──────
    start = int(trained["test_start_bar"])
    test = df.iloc[start:].reset_index(drop=True)
    if len(test) < 30:
        return {"applied": False, "reason": "short_holdout",
                "meta_model": _summarize(trained),
                "note": "El tramo reservado es demasiado corto para medir el "
                        "efecto del overlay sobre el rendimiento."}

    test_events = [e for e in events if e >= start]
    sized = meta_model.size_signals(
        trained, features, test_events,
        max_fraction=cfg.max_fraction, floor=cfg.floor,
    )
    base_fraction = _base_fraction(spec)
    sizing = conviction_sizing(sized["sizes"], base_fraction, offset=start)

    risk = spec_risk(spec)
    bt_base = backtest_signals(test, compile_signals(test, spec), costs=costs,
                               risk=risk, sizing=spec_sizing(spec))
    bt_meta = backtest_signals(test, compile_signals(test, spec), costs=costs,
                               risk=risk, sizing=sizing)

    sharpe_base = round(metrics.sharpe_ratio(bt_base["bar_returns"], ppy), 3)
    sharpe_meta = round(metrics.sharpe_ratio(bt_meta["bar_returns"], ppy), 3)
    taken = sized.get("signals_taken", 0)
    total = sized.get("signals_total", 0)

    return {
        "applied": True,
        "meta_model": _summarize(trained),
        "labels": {"n_events": labels["n_events"], "counts": labels.get("counts")},
        "sizing": {
            "mean_size_pct": round(float(sized.get("mean_size", 0.0)) * 100.0, 1),
            "signals_taken": taken,
            "signals_total": total,
            "floor": cfg.floor,
        },
        # Fuera de muestra: el tramo reservado del propio meta-modelo.
        "out_of_sample": {
            "from_bar": start,
            "candles": len(test),
            "sharpe_flat": sharpe_base,
            "sharpe_conviction": sharpe_meta,
            "sharpe_delta": round(sharpe_meta - sharpe_base, 3),
            "return_flat_pct": bt_base["total_return_pct"],
            "return_conviction_pct": bt_meta["total_return_pct"],
            "max_drawdown_flat_pct": bt_base["max_drawdown_pct"],
            "max_drawdown_conviction_pct": bt_meta["max_drawdown_pct"],
            "exposure_flat_pct": bt_base["exposure_pct"],
            "exposure_conviction_pct": bt_meta["exposure_pct"],
            "trades_flat": bt_base["total_trades"],
            "trades_conviction": bt_meta["total_trades"],
        },
        "improves": sharpe_meta > sharpe_base,
        "note": (
            f"El meta-modelo opera {taken} de {total} señales con un tamaño medio "
            f"del {round(float(sized.get('mean_size', 0.0)) * 100)}% del capital. "
            f"En el tramo que no vio al entrenar, el Sharpe pasa de {sharpe_base} "
            f"a {sharpe_meta}. "
            + ("Dimensionar por convicción mejora aquí el rendimiento ajustado a riesgo."
               if sharpe_meta > sharpe_base else
               "El filtro tiene fundamento estadístico pero no se traduce en mejor "
               "Sharpe en este tramo: aplicarlo es opcional.")
        ),
    }
