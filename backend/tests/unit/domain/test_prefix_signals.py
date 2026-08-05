"""
test_prefix_signals.py — Reutilizar el cálculo en los prefijos, sin cambiar nada.

Perfilando la evaluación de un genoma salió que el **97 % del tiempo** se iba en
`compile_signals`, y de ahí dos tercios en la librería de indicadores: cada uno
de los nueve segmentos del walk-forward recompilaba todo desde cero.

La salida se apoya en una propiedad, no en una aproximación: **todos los
indicadores del catálogo son causales**, así que el valor en la vela `i` depende
solo de velas ≤ i. De ahí se sigue que calcular sobre `df[:k]` da exactamente lo
mismo que calcular sobre el histórico entero y recortar. Los tramos de
ENTRENAMIENTO del walk-forward son prefijos; los de TEST no.

Esa propiedad es la que sostiene toda la optimización, así que se comprueba aquí
—sobre los 31 indicadores y sobre specs aleatorios— en lugar de darse por buena.
Si algún día se añade un indicador no causal, estos tests lo detectan antes de
que corrompa en silencio todos los Sharpe in-sample del motor.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services.strategy_evaluation import (
    _prefix_signals, _segment_backtest, evaluate_fitness, walk_forward_oos,
)
from core.domain.services.strategy_spec import _ALL, _series, compile_signals, random_spec


def _df(n=1500, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.012, n)))
    spread = np.abs(rng.normal(0, 0.006, n)) + 0.002
    return pd.DataFrame({
        "timestamp": [1_600_000_000_000 + i * 3_600_000 for i in range(n)],
        "open": close, "high": close * (1 + spread), "low": close * (1 - spread),
        "close": close, "volume": np.ones(n) * 1000,
    })


class TestCausality:
    """La propiedad de la que depende todo lo demás."""

    @pytest.mark.unit
    @pytest.mark.parametrize("name", sorted(_ALL))
    def test_every_indicator_is_prefix_stable(self, name):
        """Si un indicador no cumple esto, no es causal — y un indicador no
        causal en un motor de backtest es una fuga de futuro, no un detalle de
        rendimiento."""
        df = _df()
        meta = _ALL[name]
        params = {p: ((lo + hi) // 2 if kind == "int" else round((lo + hi) / 2, 2))
                  for p, (kind, lo, hi) in meta["params"].items()}
        k = 900

        full = np.asarray(_series(df, name, params, {})[:k], dtype=float)
        prefix = np.asarray(_series(df.iloc[:k], name, params, {}), dtype=float)

        both_nan = np.isnan(full) & np.isnan(prefix)
        assert (np.isclose(full, prefix, rtol=1e-9, atol=1e-9) | both_nan).all(), (
            f"{name} no es estable en prefijos: o no es causal, o mira al futuro")

    @pytest.mark.unit
    def test_signals_are_prefix_stable_for_random_specs(self):
        """Las condiciones de patrón y de cruce añaden lógica encima de los
        indicadores; que estos sean causales no basta para dar por hecho que las
        señales lo sean."""
        df = _df()
        rng = np.random.default_rng(11)
        for _ in range(25):
            spec = random_spec(rng)
            for k in (400, 800, 1200):
                full = compile_signals(df, spec)[:k]
                prefix = compile_signals(df.iloc[:k], spec)
                assert np.array_equal(full, prefix)


class TestReuse:

    @pytest.mark.unit
    def test_reusing_prefix_signals_gives_an_identical_backtest(self):
        """La optimización solo vale si NO cambia ningún resultado. Aquí se
        compara operación a operación, no solo el agregado."""
        df = _df()
        spec = random_spec(np.random.default_rng(3))
        signals_full = compile_signals(df, spec)
        k = 900
        segment = df.iloc[:k]

        recomputed = _segment_backtest(segment, spec)
        reused = _segment_backtest(segment, spec,
                                   signals=_prefix_signals(signals_full, k))

        assert recomputed["trades"] == reused["trades"]
        assert recomputed["total_return_pct"] == reused["total_return_pct"]
        assert recomputed["bar_returns"] == reused["bar_returns"]

    @pytest.mark.unit
    def test_walk_forward_is_identical_with_and_without_reuse(self):
        df = _df()
        spec = random_spec(np.random.default_rng(5))
        plain = walk_forward_oos(df, spec, n_splits=4)
        reused = walk_forward_oos(df, spec, n_splits=4,
                                  signals_full=compile_signals(df, spec))
        assert plain == reused

    @pytest.mark.unit
    def test_fitness_is_identical_for_many_random_specs(self):
        """La comprobación de fondo: si la optimización cambiara el fitness,
        cambiaría el orden del GA y con él las estrategias que encuentra."""
        df = _df()
        rng = np.random.default_rng(9)
        for _ in range(15):
            spec = random_spec(rng)
            direct = evaluate_fitness(df, spec, n_splits=4)
            # Recalcular por el camino largo, sin reutilizar nada.
            manual_full = _segment_backtest(df, spec)
            manual_wf = walk_forward_oos(df, spec, 4, 365.0)
            assert direct["n_trades"] == manual_full["total_trades"]
            assert direct["mean_oos_sharpe"] == manual_wf["mean_oos_sharpe"]
            assert direct["mean_is_sharpe"] == manual_wf["mean_is_sharpe"]

    @pytest.mark.unit
    def test_no_signals_falls_back_to_recomputing(self):
        """`None` debe comportarse como antes de existir esta ruta: es lo que
        usan los tramos de test, que no son prefijos."""
        assert _prefix_signals(None, 100) is None

    @pytest.mark.unit
    def test_the_slice_matches_the_requested_length(self):
        signals = np.arange(1000)
        assert len(_prefix_signals(signals, 400)) == 400
