"""
test_meta_model.py — Meta-modelo y sizing por convicción (G3, integración).

El primario decide DÓNDE entrar; el meta-modelo, CUÁNTO. No repite la decisión
de dirección: aprende cuándo el primario acierta, que es un problema mucho más
acotado — y cuyo peor fallo es operar de menos, nunca operar al revés.

Lo que estos tests protegen es el rigor de ese entrenamiento: partición
temporal, purga del solape, y la honestidad de declararse inútil cuando no hay
señal aprendible.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services import labeling, meta_model
from core.domain.services.backtest_execution import SizingModel, simulate


def _features(n, signal=None, seed=0):
    """Features sintéticas; `signal` es una columna con poder predictivo real."""
    rng = np.random.default_rng(seed)
    data = {f"f{i}": rng.normal(0, 1, n) for i in range(4)}
    if signal is not None:
        data["edge"] = signal
    return pd.DataFrame(data)


def _labels(n_events, hits, start=0, horizon=5):
    """Eventos etiquetados: los `hits` primeros ganan, el resto pierde."""
    return [
        {"t0": start + i * (horizon + 1), "t1": start + i * (horizon + 1) + horizon,
         "ret": 0.05 if i < hits else -0.03, "label": 1 if i < hits else -1}
        for i in range(n_events)
    ]


class TestTraining:

    @pytest.mark.unit
    def test_learns_a_real_pattern(self):
        """Feature que separa aciertos de fallos: el meta-modelo debe encontrarla
        y superar a operar todas las señales."""
        n_events, horizon = 160, 4
        rng = np.random.default_rng(3)
        wins = rng.random(n_events) < 0.5

        labels = [
            {"t0": i * (horizon + 1), "t1": i * (horizon + 1) + horizon,
             "ret": 0.04 if wins[i] else -0.03}
            for i in range(n_events)
        ]
        n_bars = labels[-1]["t1"] + 5
        # La columna `edge` vale ~1 en los eventos ganadores y ~0 en los demás.
        edge = np.zeros(n_bars)
        for i, lab in enumerate(labels):
            edge[lab["t0"]] = 1.0 if wins[i] else 0.0
        feats = _features(n_bars, signal=edge + rng.normal(0, 0.05, n_bars), seed=1)

        out = meta_model.train_meta_model(feats, labels)
        assert out["usable"] is True
        assert out["edge_over_primary"] > 0
        assert out["meta_precision"] > out["primary_hit_rate"]

    @pytest.mark.unit
    def test_says_so_when_there_is_nothing_to_learn(self):
        """Features de puro ruido: declararse inútil es más honesto que devolver
        una probabilidad con apariencia de convicción."""
        labels = _labels(120, hits=60, horizon=4)
        n_bars = labels[-1]["t1"] + 5
        out = meta_model.train_meta_model(_features(n_bars, seed=9), labels)

        assert out["usable"] is False
        assert "no aporta" in out["note"] or "no mejora" in out["note"]

    @pytest.mark.unit
    def test_refuses_with_too_few_events(self):
        labels = _labels(8, hits=4)
        out = meta_model.train_meta_model(_features(80), labels)
        assert out["usable"] is False
        assert "insuficientes" in out["note"] or "evaluación" in out["note"]

    @pytest.mark.unit
    def test_refuses_when_the_primary_never_fails(self):
        """Sin variación en la etiqueta no hay nada que discriminar."""
        labels = _labels(120, hits=120, horizon=4)
        n_bars = labels[-1]["t1"] + 5
        out = meta_model.train_meta_model(_features(n_bars), labels)
        assert out["usable"] is False

    @pytest.mark.unit
    def test_purges_the_overlap_between_train_and_test(self):
        """Las muestras cuyo horizonte invade el tramo de evaluación se
        descartan del entrenamiento. Aquí SÍ aplica el purging del libro,
        porque aquí sí se entrena un modelo."""
        labels = _labels(140, hits=70, horizon=4)
        n_bars = labels[-1]["t1"] + 5
        feats = _features(n_bars, seed=2)

        strict = meta_model.train_meta_model(
            feats, labels, config=meta_model.MetaModelConfig(embargo_bars=40))
        loose = meta_model.train_meta_model(
            feats, labels, config=meta_model.MetaModelConfig(embargo_bars=0))

        assert strict.get("n_train", 0) < loose.get("n_train", 1)

    @pytest.mark.unit
    def test_never_uses_a_random_split(self):
        """El tramo de evaluación es SIEMPRE el final de la serie. Un split
        aleatorio entrenaría con el futuro y daría precisiones que no existen."""
        labels = _labels(140, hits=70, horizon=4)
        n_bars = labels[-1]["t1"] + 5
        out = meta_model.train_meta_model(_features(n_bars, seed=4), labels)
        # Entrenamiento y test no se solapan y el test es minoría (30%).
        assert out["n_train"] + out["n_test"] <= out["n_events"]
        assert out["n_test"] < out["n_train"]


class TestSizing:

    @pytest.mark.unit
    def test_falls_back_to_full_size_when_unusable(self):
        """Sin convicción medible se opera como siempre, en lugar de inventarse
        una modulación."""
        out = meta_model.size_signals({"usable": False}, _features(50), [10, 20])
        assert out["applied"] is False
        assert set(out["sizes"].values()) == {1.0}

    @pytest.mark.unit
    def test_scales_size_with_probability(self):
        class _Stub:
            """Devuelve una probabilidad creciente con la primera feature."""
            @staticmethod
            def predict_proba(X):
                p = float(np.clip(X[0][0], 0.0, 1.0))
                return np.array([[1 - p, p]])

        feats = pd.DataFrame({"f0": [0.2, 0.6, 0.95], "f1": [0.0, 0.0, 0.0]})
        out = meta_model.size_signals(
            {"usable": True, "model": _Stub()}, feats, [0, 1, 2], floor=0.5)

        assert out["applied"] is True
        assert out["sizes"][0] == 0.0                 # convicción bajo el suelo
        assert out["sizes"][1] < out["sizes"][2]      # y escala con la confianza
        assert out["signals_taken"] == 2


class TestConvictionSizingInTheEngine:

    @staticmethod
    def _prices(n=40):
        return np.linspace(100, 140, n)

    @pytest.mark.unit
    def test_conviction_scales_the_position(self):
        """Media convicción invierte la mitad: la separación dirección/tamaño
        llega hasta el motor."""
        close = self._prices()
        signals = np.zeros(close.size); signals[5] = 1; signals[30] = -1

        full = simulate(close, close, close, signals,
                        sizing=SizingModel(mode="conviction", conviction=((6, 1.0),)))
        half = simulate(close, close, close, signals,
                        sizing=SizingModel(mode="conviction", conviction=((6, 0.5),)))

        gain_full = full["final_capital"] - 10_000
        gain_half = half["final_capital"] - 10_000
        assert gain_half == pytest.approx(gain_full / 2, rel=0.02)

    @pytest.mark.unit
    def test_zero_conviction_skips_the_trade(self):
        """No operar es una decisión, no un caso degenerado."""
        close = self._prices()
        signals = np.zeros(close.size); signals[5] = 1; signals[30] = -1

        out = simulate(close, close, close, signals,
                       sizing=SizingModel(mode="conviction", conviction=((6, 0.0),)))
        assert out["trades"] == []
        assert out["final_capital"] == pytest.approx(10_000)

    @pytest.mark.unit
    def test_unknown_bar_falls_back_to_the_default_fraction(self):
        """Una señal sin convicción asignada no se anula: degrada a la política
        previa."""
        close = self._prices()
        signals = np.zeros(close.size); signals[5] = 1; signals[30] = -1

        out = simulate(close, close, close, signals,
                       sizing=SizingModel(mode="conviction", fraction=0.25, conviction=()))
        assert len(out["trades"]) == 1
        assert out["final_capital"] > 10_000

    @pytest.mark.unit
    def test_other_sizing_modes_are_untouched(self):
        """El modo nuevo no puede alterar el comportamiento de los existentes."""
        close = self._prices()
        signals = np.zeros(close.size); signals[5] = 1; signals[30] = -1

        full = simulate(close, close, close, signals, sizing=SizingModel(mode="full"))
        assert len(full["trades"]) == 1
        assert full["final_capital"] > 10_000


class TestEndToEnd:

    @pytest.mark.unit
    def test_labels_feed_the_meta_model(self):
        """El circuito completo: triple-barrera → meta-etiquetas → entrenamiento.
        Lo que se comprueba es que las piezas encajan, no el rendimiento."""
        rng = np.random.default_rng(11)
        close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, 500)))
        df = pd.DataFrame({
            "timestamp": range(500), "open": close,
            "high": close * 1.01, "low": close * 0.99,
            "close": close, "volume": np.ones(500),
        })

        labeled = labeling.triple_barrier_labels(
            df, event_indices=list(range(50, 450, 4)),
            config=labeling.BarrierConfig(horizon=8),
        )
        assert labeled["n_events"] > 40

        out = meta_model.train_meta_model(_features(500, seed=6), labeled["labels"])
        assert "usable" in out
        assert isinstance(out["usable"], bool)
