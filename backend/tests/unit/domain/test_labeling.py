"""
test_labeling.py — Triple-barrera, meta-etiquetado y bet sizing (G3).

Una regla de salida fija responde a la pregunta equivocada. Lo que hay que saber
de una entrada es qué pasó primero: objetivo, stop u horizonte agotado. Y las
barreras tienen que escalar con la volatilidad **estimada hasta la entrada**,
porque usar la posterior sería mirar el futuro.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services import labeling as lab


def _df(close, high=None, low=None):
    close = np.asarray(close, dtype=float)
    high = close if high is None else np.asarray(high, dtype=float)
    low = close if low is None else np.asarray(low, dtype=float)
    return pd.DataFrame({
        "timestamp": [1_700_000_000_000 + i * 86_400_000 for i in range(close.size)],
        "open": close, "high": high, "low": low, "close": close,
        "volume": np.ones(close.size),
    })


def _noisy(n=300, seed=4):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, n)))
    return _df(close, close * 1.01, close * 0.99)


class TestRealizedVolatility:

    @pytest.mark.unit
    def test_uses_only_past_data(self):
        """Un salto en la vela i no puede aparecer en la σ de la vela i: si lo
        hiciera, las barreras se estarían dimensionando con el futuro."""
        close = np.concatenate([np.full(40, 100.0), [200.0], np.full(20, 200.0)])
        vol = lab.realized_volatility(close, window=20)

        jump = 40
        assert vol[jump] == pytest.approx(0.0, abs=1e-9)   # antes del salto, plano
        assert vol[jump + 1] > 0                            # el salto ya cuenta

    @pytest.mark.unit
    def test_never_returns_nan(self):
        """Las primeras velas no tienen ventana; rellenarlas con cero abriría
        barreras de anchura nula."""
        vol = lab.realized_volatility(_noisy(60)["close"].to_numpy(), window=20)
        assert np.all(np.isfinite(vol))


class TestTripleBarrier:

    @pytest.mark.unit
    def test_labels_target_stop_and_timeout(self):
        out = lab.triple_barrier_labels(_noisy())
        assert out["n_events"] > 0
        assert set(out["counts"]) == {"target", "stop", "timeout"}
        assert sum(out["counts"].values()) == out["n_events"]
        assert all(l["label"] in (-1, 0, 1) for l in out["labels"])

    @pytest.mark.unit
    def test_a_clean_rally_hits_the_upper_barrier(self):
        """Sube sin retrocesos tras un tramo volátil: la etiqueta debe ser +1."""
        rng = np.random.default_rng(1)
        warmup = 100 + np.cumsum(rng.normal(0, 1.0, 60))
        rally = warmup[-1] * np.cumprod(np.full(20, 1.05))
        close = np.concatenate([warmup, rally])
        out = lab.triple_barrier_labels(
            _df(close, close * 1.001, close * 0.999),
            event_indices=[60],
            config=lab.BarrierConfig(profit_mult=1.0, stop_mult=1.0, horizon=10),
        )
        assert out["labels"][0]["label"] == 1

    @pytest.mark.unit
    def test_stop_wins_when_both_barriers_are_touched_in_one_bar(self):
        """No se puede saber cuál llegó antes dentro de la vela; suponer lo
        favorable es el sesgo que hace que un backtest prometa de más."""
        rng = np.random.default_rng(2)
        warmup = 100 + np.cumsum(rng.normal(0, 1.0, 60))
        base = warmup[-1]
        close = np.concatenate([warmup, [base, base]])
        # La vela siguiente barre ambos extremos.
        high = np.concatenate([warmup * 1.001, [base * 1.5, base]])
        low = np.concatenate([warmup * 0.999, [base * 0.5, base]])

        out = lab.triple_barrier_labels(
            _df(close, high, low), event_indices=[59],
            config=lab.BarrierConfig(profit_mult=0.5, stop_mult=0.5, horizon=3),
        )
        assert out["labels"][0]["label"] == -1

    @pytest.mark.unit
    def test_flat_market_times_out(self):
        """Sin movimiento no se toca ninguna barrera horizontal: etiqueta 0."""
        rng = np.random.default_rng(3)
        warmup = 100 + np.cumsum(rng.normal(0, 0.8, 60))
        close = np.concatenate([warmup, np.full(20, warmup[-1])])
        out = lab.triple_barrier_labels(
            _df(close), event_indices=[60],
            config=lab.BarrierConfig(profit_mult=3.0, stop_mult=3.0, horizon=8),
        )
        assert out["labels"][0]["label"] == 0
        assert out["labels"][0]["bars_held"] == 8

    @pytest.mark.unit
    def test_wider_barriers_take_longer_to_resolve(self):
        df = _noisy()
        tight = lab.triple_barrier_labels(df, config=lab.BarrierConfig(profit_mult=0.5, stop_mult=0.5))
        wide = lab.triple_barrier_labels(df, config=lab.BarrierConfig(profit_mult=5.0, stop_mult=5.0))

        tight_held = np.mean([l["bars_held"] for l in tight["labels"]])
        wide_held = np.mean([l["bars_held"] for l in wide["labels"]])
        assert wide_held > tight_held
        assert wide["counts"]["timeout"] > tight["counts"]["timeout"]

    @pytest.mark.unit
    def test_short_series_reports_instead_of_crashing(self):
        assert lab.triple_barrier_labels(_df(np.full(10, 100.0)))["n_events"] == 0


class TestAverageUniqueness:

    @pytest.mark.unit
    def test_overlapping_labels_weigh_less(self):
        """Dos operaciones sobre las mismas velas comparten los mismos retornos:
        no son dos observaciones independientes."""
        overlapping = [{"t0": 0, "t1": 9}, {"t0": 0, "t1": 9}]
        disjoint = [{"t0": 0, "t1": 9}, {"t0": 10, "t1": 19}]

        w_over = lab.average_uniqueness(overlapping, 20)
        w_disj = lab.average_uniqueness(disjoint, 20)

        assert np.allclose(w_over, 0.5)
        assert np.allclose(w_disj, 1.0)

    @pytest.mark.unit
    def test_empty_input_is_safe(self):
        assert lab.average_uniqueness([], 10).size == 0


class TestMetaLabeling:

    @pytest.mark.unit
    def test_learns_when_the_primary_is_right(self):
        labels = [{"t0": 0, "t1": 2, "ret": 0.05}, {"t0": 3, "t1": 5, "ret": -0.03}]
        out = lab.meta_label(labels)
        assert out["y"] == [1, 0]
        assert out["hit_rate"] == 50.0

    @pytest.mark.unit
    def test_respects_the_side_proposed_by_the_primary(self):
        """En corto, una caída es un acierto."""
        labels = [{"t0": 0, "t1": 2, "ret": -0.05}]
        assert lab.meta_label(labels, primary_side=[-1])["y"] == [1]
        assert lab.meta_label(labels, primary_side=[1])["y"] == [0]

    @pytest.mark.unit
    def test_carries_sample_weights_for_the_non_iid_problem(self):
        labels = [{"t0": 0, "t1": 5, "ret": 0.01}, {"t0": 0, "t1": 5, "ret": 0.02}]
        out = lab.meta_label(labels)
        assert len(out["sample_weights"]) == 2
        assert all(w < 1.0 for w in out["sample_weights"])   # solapan → pesan menos

    @pytest.mark.unit
    def test_mismatched_side_length_is_rejected(self):
        assert lab.meta_label([{"t0": 0, "t1": 1, "ret": 0.1}], primary_side=[1, -1])["n"] == 0


class TestBetSize:

    @pytest.mark.unit
    def test_no_conviction_means_no_position(self):
        """No operar es una decisión, y la más rentable sin ventaja."""
        assert lab.bet_size(0.5) == 0.0
        assert lab.bet_size(0.3) == 0.0

    @pytest.mark.unit
    def test_size_grows_with_confidence(self):
        assert lab.bet_size(0.6) < lab.bet_size(0.8) < lab.bet_size(0.95)

    @pytest.mark.unit
    def test_is_capped(self):
        assert lab.bet_size(1.0) == pytest.approx(1.0)
        assert lab.bet_size(1.0, max_fraction=0.25) == pytest.approx(0.25)

    @pytest.mark.unit
    @pytest.mark.parametrize("p", [-0.5, 1.5])
    def test_out_of_range_probabilities_are_clamped(self, p):
        assert 0.0 <= lab.bet_size(p) <= 1.0
