"""
test_triple_barrier_exit.py — La triple barrera como política de salida.

Una regla de salida técnica —«vende si el RSI sube de 70»— responde a la
pregunta equivocada. Lo que hay que saber de una entrada es **qué pasó
primero**: objetivo, stop o agotamiento del horizonte.

Esa geometría ya se podía etiquetar (`labeling.py`); lo que faltaba era poder
**operarla**, y que el GA pudiera evolucionarla. Se implementa reutilizando la
gestión intrabar del motor (`atr_stop_mult` + `atr_target_mult` + `max_bars`) en
lugar de un motor de salidas aparte.

Lo que se fija aquí:
  · el objetivo por ATR se mide desde el precio de ENTRADA, con el ATR de la
    barra de entrada (no el de la barra de salida: sería mirar el futuro);
  · cuando hay objetivo fijo y objetivo por ATR, manda el más cercano — el que
    de verdad va a cerrar la operación;
  · un spec sin estos campos se comporta EXACTAMENTE igual que antes.
"""

import numpy as np
import pytest

from core.domain.services.backtest_execution import RiskModel, simulate
from core.domain.services.strategy_spec import (
    RISK_RANGES, _random_risk, describe_spec, spec_risk, validate_spec,
)


def _flat_atr(n, value=1.0):
    return np.full(n, float(value))


class TestAtrTarget:

    @pytest.mark.unit
    def test_target_fires_at_entry_plus_multiple_of_atr(self):
        """La señal de la vela 0 se rellena a la apertura de la 1 (100), así que
        con ATR 1 y objetivo 3×ATR la barrera superior está en 103."""
        close = np.array([100.0, 100.0, 101.0, 104.0, 104.0])
        high = np.array([100.0, 100.0, 101.5, 104.0, 104.0])
        low = np.array([100.0, 99.5, 100.5, 102.0, 103.0])
        signals = np.array([1, 0, 0, 0, 0])

        out = simulate(close, high, low, signals, 10_000.0,
                       risk=RiskModel(atr_target_mult=3.0), atr=_flat_atr(5),
                       open_=close)

        assert len(out["trades"]) == 1
        trade = out["trades"][0]
        assert trade["exit_reason"] == "take_profit"
        assert trade["exit_price"] == pytest.approx(103.0)  # entry(100) + 3·ATR

    @pytest.mark.unit
    def test_nearest_target_wins_between_fixed_and_atr(self):
        """Con objetivo fijo y objetivo por ATR gana el más CERCANO: es el que
        el precio toca antes, y por tanto el que cierra la operación."""
        close = np.array([100.0, 100.0, 100.0, 130.0, 130.0])
        high = np.array([100.0, 100.0, 100.0, 130.0, 130.0])
        low = np.array([100.0, 100.0, 100.0, 100.0, 130.0])
        signals = np.array([1, 0, 0, 0, 0])

        # Fijo: +20% = 120. ATR: 100 + 5·1 = 105. Debe ganar 105.
        out = simulate(close, high, low, signals, 10_000.0,
                       risk=RiskModel(take_profit_pct=0.20, atr_target_mult=5.0),
                       atr=_flat_atr(5), open_=close)

        assert out["trades"][0]["exit_price"] == pytest.approx(105.0)

    @pytest.mark.unit
    def test_stop_wins_over_target_in_the_same_candle(self):
        """La convención conservadora no cambia por usar barreras de ATR: si en
        la misma vela se tocan las dos, salta el stop. Suponer lo favorable es
        el sesgo que hace que un backtest prometa lo que la ejecución no da."""
        close = np.array([100.0, 100.0, 100.0, 100.0])
        high = np.array([100.0, 100.0, 100.0, 110.0])
        low = np.array([100.0, 100.0, 100.0, 90.0])
        signals = np.array([1, 0, 0, 0])

        out = simulate(close, high, low, signals, 10_000.0,
                       risk=RiskModel(atr_stop_mult=2.0, atr_target_mult=3.0),
                       atr=_flat_atr(4), open_=close)

        assert out["trades"][0]["exit_reason"] == "atr_stop"

    @pytest.mark.unit
    def test_vertical_barrier_closes_what_neither_side_resolves(self):
        """El tercer lado: si en el horizonte no se toca ni objetivo ni stop, la
        posición se cierra igual. Sin él, un trade puede vivir para siempre."""
        close = np.array([100.0] * 10)
        signals = np.array([1] + [0] * 9)

        out = simulate(close, close, close, signals, 10_000.0,
                       risk=RiskModel(atr_stop_mult=5.0, atr_target_mult=5.0, max_bars=3),
                       atr=_flat_atr(10), open_=close)

        assert out["trades"][0]["exit_reason"] == "time_exit"

    @pytest.mark.unit
    def test_absent_field_changes_nothing(self):
        """Compatibilidad: toda estrategia ya guardada carece del campo nuevo y
        debe seguir comportándose exactamente igual."""
        rng = np.random.default_rng(4)
        close = 100 * np.exp(np.cumsum(rng.normal(0.001, 0.02, 200)))
        signals = np.where(np.arange(200) % 20 == 0, 1,
                           np.where(np.arange(200) % 20 == 10, -1, 0))
        risk = RiskModel(stop_loss_pct=0.05, take_profit_pct=0.10)

        before = simulate(close, close * 1.01, close * 0.99, signals, 10_000.0,
                          risk=risk, open_=close)
        after = simulate(close, close * 1.01, close * 0.99, signals, 10_000.0,
                         risk=RiskModel(stop_loss_pct=0.05, take_profit_pct=0.10,
                                        atr_target_mult=None), open_=close)
        assert before["trades"] == after["trades"]


class TestSpecIntegration:

    @pytest.mark.unit
    def test_spec_risk_carries_the_target(self):
        model = spec_risk({"risk": {"atr_stop_mult": 2.0, "atr_target_mult": 4.0,
                                    "max_bars": 20}})
        assert model.atr_target_mult == 4.0
        assert model.active is True

    @pytest.mark.unit
    def test_the_range_is_declared_so_validation_and_jitter_pick_it_up(self):
        """Validación y jitter son genéricos sobre RISK_RANGES: declarar el
        rango basta para que el GA lo evolucione legalmente."""
        assert "atr_target_mult" in RISK_RANGES
        assert validate_spec(_spec_with({"atr_stop_mult": 2.0, "atr_target_mult": 4.0}))
        assert not validate_spec(_spec_with({"atr_target_mult": 99.0}))

    @pytest.mark.unit
    def test_generator_produces_triple_barrier_specs(self):
        """Si el GA nunca la genera, la política de salida es código muerto."""
        rng = np.random.default_rng(0)
        blocks = [_random_risk(rng) for _ in range(400)]
        triples = [b for b in blocks
                   if b and b.get("atr_stop_mult") and b.get("atr_target_mult")]
        assert triples, "El generador nunca produce una triple barrera."
        # Los tres lados van siempre juntos: media barrera no es la política.
        assert all(b.get("max_bars") for b in triples)

    @pytest.mark.unit
    def test_generated_barriers_are_asymmetric_upward(self):
        """2σ arriba y 1σ abajo es lo que hace rentable acertar menos de la
        mitad de las veces. Un objetivo más cerca que el stop invierte eso."""
        rng = np.random.default_rng(1)
        triples = [b for b in (_random_risk(rng) for _ in range(400))
                   if b and b.get("atr_stop_mult") and b.get("atr_target_mult")]
        assert all(b["atr_target_mult"] > b["atr_stop_mult"] for b in triples)

    @pytest.mark.unit
    def test_description_names_the_policy(self):
        """Las tres barreras juntas tienen nombre propio; enumerarlas por
        separado esconde que son una sola decisión."""
        text = describe_spec(_spec_with({"atr_stop_mult": 2.0, "atr_target_mult": 4.0,
                                         "max_bars": 20}))
        assert "triple barrera" in text
        assert "20 velas" in text


def _spec_with(risk: dict) -> dict:
    return {
        "entry": {"combine": "AND", "conditions": [
            {"type": "threshold", "indicator": "RSI", "params": {"window": 14},
             "op": "lt", "threshold": 30.0}]},
        "exit": {"combine": "OR", "conditions": [
            {"type": "threshold", "indicator": "RSI", "params": {"window": 14},
             "op": "gt", "threshold": 70.0}]},
        "risk": risk,
    }
