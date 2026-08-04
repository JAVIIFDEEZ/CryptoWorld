"""
test_meta_sizing.py — El meta-modelo dimensionando un spec real.

Lo que se fija aquí es lo que separa este overlay de un adorno:

  · el mapa de convicción se indexa por la vela de RELLENO, no por la de la
    señal (si no, el tamaño se decidiría con el cierre de la vela en cuya
    apertura se opera);
  · la mejora se mide fuera del tramo de entrenamiento;
  · sin edge medible, no se aplica — y se dice.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services import meta_sizing
from core.domain.services.backtest_execution import CostModel, simulate


def _df(n=600, seed=7):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0.0008, 0.02, n)))
    return pd.DataFrame({
        "timestamp": [1_600_000_000_000 + i * 86400000 for i in range(n)],
        "open": close, "high": close * 1.012, "low": close * 0.988,
        "close": close, "volume": rng.uniform(800, 1200, n),
    })


SPEC = {
    "entry": {"combine": "AND", "conditions": [
        {"type": "threshold", "indicator": "RSI", "params": {"window": 14},
         "op": "lt", "threshold": 45.0},
    ]},
    "exit": {"combine": "OR", "conditions": [
        {"type": "threshold", "indicator": "RSI", "params": {"window": 14},
         "op": "gt", "threshold": 60.0},
    ]},
}


class TestFeatures:

    @pytest.mark.unit
    def test_features_do_not_look_ahead(self):
        """Truncar el futuro no puede cambiar las features del pasado. Es la
        comprobación que detecta cualquier ventana centrada o `shift(-1)`."""
        df = _df()
        full = meta_sizing.market_features(df)
        cut = meta_sizing.market_features(df.iloc[:400])
        common = full.iloc[:400].to_numpy(dtype=float)
        partial = cut.to_numpy(dtype=float)
        assert np.allclose(common, partial, equal_nan=True)

    @pytest.mark.unit
    def test_features_are_few_on_purpose(self):
        """Más features sobre unos cientos de eventos es superficie de
        sobreajuste, no información."""
        assert meta_sizing.market_features(_df()).shape[1] <= 12


class TestConvictionIndexing:

    @pytest.mark.unit
    def test_size_lands_on_the_fill_bar_not_the_signal_bar(self):
        """La señal de `s` se rellena en la apertura de `s+1`, y es ahí donde el
        motor consulta el tamaño. Indexar por `s` aplicaría la convicción a la
        operación equivocada."""
        sizing = meta_sizing.conviction_sizing({10: 0.3}, base_fraction=1.0)
        assert sizing.conviction_at(11) == pytest.approx(0.3)
        assert sizing.conviction_at(10) == pytest.approx(1.0)  # repliegue

    @pytest.mark.unit
    def test_offset_reindexes_to_a_segment(self):
        sizing = meta_sizing.conviction_sizing({100: 0.4}, offset=90)
        assert sizing.conviction_at(11) == pytest.approx(0.4)

    @pytest.mark.unit
    def test_indices_before_the_segment_are_dropped(self):
        sizing = meta_sizing.conviction_sizing({5: 0.4}, offset=90)
        assert sizing.conviction == ()

    @pytest.mark.unit
    def test_zero_conviction_means_the_trade_is_not_taken(self):
        """El suelo de convicción no reduce el tamaño: cancela la operación.
        No operar es una decisión, y la correcta cuando no hay ventaja."""
        close = np.array([100.0, 100.0, 105.0, 110.0, 108.0])
        signals = np.array([1, 0, 0, -1, 0])
        sizing = meta_sizing.conviction_sizing({0: 0.0})
        out = simulate(close, close, close, signals, 10_000.0, sizing=sizing,
                       open_=close)
        assert out["trades"] == []


def _learnable_df(n=3000, seed=11):
    """
    Serie con dos regímenes alternos: en el tranquilo el mercado sube, en el
    convulso cae con el triple de volatilidad. La señal de reversión entra en
    ambos, así que **hay algo que aprender**: cuándo esa entrada acierta.

    Hace falta un caso así para ejercitar la rama en que el overlay SÍ se aplica.
    Sobre ruido puro el meta-modelo no encuentra edge — y no debe encontrarlo.
    """
    rng = np.random.default_rng(seed)
    calm = np.array([(i // 60) % 2 == 0 for i in range(n)])
    drift = np.where(calm, 0.006, -0.006)
    vol = np.where(calm, 0.010, 0.035)
    close = 100 * np.exp(np.cumsum(rng.normal(drift, vol)))
    return pd.DataFrame({
        "timestamp": [1_600_000_000_000 + i * 86400000 for i in range(n)],
        "open": close, "high": close * (1 + vol), "low": close * (1 - vol),
        "close": close, "volume": rng.uniform(800, 1200, n),
    })


@pytest.fixture(scope="module")
def learnable():
    """El overlay sobre la serie con régimen aprendible (caro: se comparte)."""
    return meta_sizing.conviction_overlay(
        _learnable_df(), SPEC, costs=CostModel(commission_bps=10.0, slippage_bps=5.0))


class TestOverlay:

    @pytest.mark.unit
    def test_refuses_to_train_without_enough_events(self):
        out = meta_sizing.conviction_overlay(_df(n=120), SPEC)
        assert out["applied"] is False
        assert out["reason"] in ("insufficient_events", "unlabelable", "no_edge")

    @pytest.mark.unit
    def test_verdict_is_always_legible(self):
        out = meta_sizing.conviction_overlay(
            _df(), SPEC, costs=CostModel(commission_bps=10.0, slippage_bps=5.0))
        assert isinstance(out["applied"], bool)
        assert out["note"]

    @pytest.mark.unit
    def test_when_applied_the_comparison_is_out_of_sample(self, learnable):
        """La mejora se mide en el tramo que el meta-modelo no vio: entrenar y
        medir sobre todo el histórico daría siempre mejora, y sería falsa."""
        oos = learnable["out_of_sample"]
        assert oos["from_bar"] > 0
        assert oos["candles"] >= 30
        assert learnable["meta_model"]["test_start_bar"] == oos["from_bar"]

    @pytest.mark.unit
    def test_finds_the_edge_when_there_is_one_to_find(self, learnable):
        """Contraparte obligada de `test_no_edge_is_reported_not_hidden`: un
        detector que nunca dice que sí no está midiendo nada."""
        assert learnable["applied"] is True
        assert learnable["meta_model"]["edge_over_primary"] > 0

    @pytest.mark.unit
    def test_conviction_reduces_exposure_rather_than_adding_it(self, learnable):
        """El meta-modelo solo puede encoger la apuesta, nunca invertir la señal
        ni apalancarla. Es el modo de fallo benigno que justifica separar
        dirección de tamaño."""
        oos = learnable["out_of_sample"]
        assert oos["exposure_conviction_pct"] <= oos["exposure_flat_pct"]

    @pytest.mark.unit
    def test_no_edge_is_reported_not_hidden(self):
        """Un meta-modelo que no supera al primario no debe usarse; devolver el
        motivo es más útil que un tamaño modulado sin fundamento."""
        flat = pd.DataFrame({
            "timestamp": [1_600_000_000_000 + i * 86400000 for i in range(400)],
            "open": [100.0] * 400, "high": [100.0] * 400, "low": [100.0] * 400,
            "close": [100.0] * 400, "volume": [1000.0] * 400,
        })
        out = meta_sizing.conviction_overlay(flat, SPEC)
        assert out["applied"] is False
        assert out["note"]

    @pytest.mark.unit
    def test_risk_sizing_is_declared_incomparable_not_silently_replaced(self):
        """Dimensionar por riesgo parte del stop-loss, y el modo por convicción
        no puede expresar ese criterio. Aplicarlo igual cambiaría dos cosas a la
        vez y el delta no sería atribuible a ninguna."""
        spec = {**SPEC, "sizing": {"mode": "risk", "risk_pct": 0.02}}
        out = meta_sizing.conviction_overlay(_df(), spec)
        assert out["applied"] is False
        assert out["reason"] == "incompatible_sizing"

    @pytest.mark.unit
    def test_fraction_sizing_is_the_fallback_for_signals_without_conviction(self):
        """Ausencia de convicción degrada a la política previa del spec, no a
        invertir todo el capital."""
        spec = {**SPEC, "sizing": {"mode": "fraction", "fraction": 0.4}}
        assert meta_sizing._base_fraction(spec) == pytest.approx(0.4)

    @pytest.mark.unit
    def test_the_overlay_never_bets_more_than_the_spec_already_did(self):
        """El techo es el tamaño propio del spec: el meta-modelo solo puede
        encoger la apuesta. Es lo que hace benigno su modo de fallo."""
        spec = {**SPEC, "sizing": {"mode": "fraction", "fraction": 0.4}}
        out = meta_sizing.conviction_overlay(_learnable_df(), spec)
        if not out["applied"]:
            pytest.skip("Sin meta-modelo utilizable no hay techo que comprobar.")
        assert out["sizing"]["mean_size_pct"] <= 40.0

    @pytest.mark.unit
    def test_the_trained_estimator_never_travels_in_the_payload(self):
        """El resultado se serializa a JSON (DRF/Celery-Redis): un
        RandomForest dentro reventaría el pipeline."""
        out = meta_sizing.conviction_overlay(_df(), SPEC)
        assert "model" not in out.get("meta_model", {})
        assert "feature_names" not in out.get("meta_model", {})
