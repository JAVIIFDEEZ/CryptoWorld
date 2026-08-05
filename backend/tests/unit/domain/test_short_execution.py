"""
test_short_execution.py — Posiciones cortas en el motor de ejecución.

Un corto NO es un largo con el signo cambiado, y tratarlo así produce un
backtest que parece funcionar y miente en cuatro sitios distintos:

  1. **La contabilidad.** Al abrir se vende algo prestado: la caja SUBE y queda
     un pasivo. El beneficio es `entrada − salida`, no `salida − entrada`.
  2. **El deslizamiento.** Quien vende recibe algo MENOS que el precio de
     referencia y quien recompra paga algo MÁS. Aplicarlo con el mismo signo
     que en un largo regalaría al corto un precio mejor que el de mercado en
     los dos extremos.
  3. **El riesgo.** Un largo pierde como mucho el 100 %; un corto no tiene tope.
     Su stop va POR ENCIMA de la entrada y su objetivo por debajo.
  4. **La financiación.** Un rate positivo significa «los largos pagan a los
     cortos»: el mismo número que es coste en un lado es INGRESO en el otro.

Y una garantía que sostiene todo lo ya construido: sin señales de corto, el
motor se comporta EXACTAMENTE como antes.
"""

import numpy as np
import pytest

from core.domain.services.backtest_execution import CostModel, RiskModel, simulate


def _flat(n, value=100.0):
    return np.full(n, float(value))


class TestAccounting:

    @pytest.mark.unit
    def test_a_short_wins_when_the_price_falls(self):
        close = np.array([100.0, 100.0, 90.0, 90.0])
        shorts = np.array([1, 0, -1, 0])
        out = simulate(close, close, close, np.zeros(4, dtype=int), 10_000.0,
                       open_=close, short_signals=shorts)

        assert len(out["trades"]) == 1
        trade = out["trades"][0]
        assert trade["side"] == "short"
        assert trade["pnl_pct"] == pytest.approx(10.0, abs=0.01)
        assert out["final_capital"] > 10_000.0

    @pytest.mark.unit
    def test_a_short_loses_when_the_price_rises(self):
        close = np.array([100.0, 100.0, 110.0, 110.0])
        shorts = np.array([1, 0, -1, 0])
        out = simulate(close, close, close, np.zeros(4, dtype=int), 10_000.0,
                       open_=close, short_signals=shorts)
        assert out["trades"][0]["pnl_pct"] == pytest.approx(-10.0, abs=0.01)
        assert out["final_capital"] < 10_000.0

    @pytest.mark.unit
    def test_the_short_pnl_is_not_the_long_pnl_with_the_sign_flipped(self):
        """Con costes, los dos lados pagan comisión y deslizamiento en su contra.
        Si el corto fuera el largo negado, uno de los dos saldría con los costes
        a favor."""
        close = np.array([100.0, 100.0, 90.0, 90.0])
        costs = CostModel(commission_bps=10.0, slippage_bps=5.0)

        short = simulate(close, close, close, np.zeros(4, dtype=int), 10_000.0,
                         costs=costs, open_=close,
                         short_signals=np.array([1, 0, -1, 0]))
        long_ = simulate(close, close, close, np.array([1, 0, -1, 0]), 10_000.0,
                         costs=costs, open_=close)

        # Ante la misma caída del 10 %, los costes empujan a los DOS lados en su
        # contra: al corto le recortan la ganancia por debajo del 10 % y al largo
        # le agrandan la pérdida por encima. Si el corto fuera el largo negado,
        # los costes le saldrían a favor a uno de los dos.
        assert 0.0 < short["trades"][0]["pnl_pct"] < 10.0
        assert long_["trades"][0]["pnl_pct"] < -10.0

    @pytest.mark.unit
    def test_slippage_hurts_the_short_on_both_legs(self):
        """Vender por debajo y recomprar por encima: el deslizamiento resta dos
        veces, igual que en un largo."""
        close = np.array([100.0, 100.0, 100.0, 100.0])
        shorts = np.array([1, 0, -1, 0])
        free = simulate(close, close, close, np.zeros(4, dtype=int), 10_000.0,
                        open_=close, short_signals=shorts)
        slipped = simulate(close, close, close, np.zeros(4, dtype=int), 10_000.0,
                           costs=CostModel(slippage_bps=50.0), open_=close,
                           short_signals=shorts)
        # Sin movimiento de precio, el corto sin costes empata y el otro pierde.
        assert free["trades"][0]["pnl_pct"] == pytest.approx(0.0, abs=0.01)
        assert slipped["trades"][0]["pnl_pct"] < -0.5

    @pytest.mark.unit
    def test_equity_reflects_the_liability_not_just_the_cash(self):
        """Al abrir un corto la caja sube, pero el patrimonio NO: queda un pasivo
        por recomprar. Confundirlos haría que abrir un corto pareciera un
        beneficio instantáneo."""
        close = _flat(4)
        out = simulate(close, close, close, np.zeros(4, dtype=int), 10_000.0,
                       open_=close, short_signals=np.array([1, 0, 0, 0]))
        # Tras abrir (vela 1) el patrimonio sigue siendo ~10 000, no 20 000.
        assert out["equity_curve"][2] == pytest.approx(10_000.0, abs=1.0)


class TestRiskMirrored:

    @pytest.mark.unit
    def test_the_stop_of_a_short_is_ABOVE_the_entry(self):
        """Es lo que acota una pérdida sin tope. Un stop por debajo sería un
        objetivo disfrazado de stop."""
        close = np.array([100.0, 100.0, 100.0, 100.0])
        high = np.array([100.0, 100.0, 100.0, 106.0])
        low = np.array([100.0, 100.0, 100.0, 100.0])
        out = simulate(close, high, low, np.zeros(4, dtype=int), 10_000.0,
                       risk=RiskModel(stop_loss_pct=0.05), open_=close,
                       short_signals=np.array([1, 0, 0, 0]))
        trade = out["trades"][0]
        assert trade["exit_reason"] == "stop_loss"
        assert trade["exit_price"] > trade["entry_price"]

    @pytest.mark.unit
    def test_the_target_of_a_short_is_BELOW_the_entry(self):
        close = np.array([100.0, 100.0, 100.0, 90.0])
        high = np.array([100.0, 100.0, 100.0, 100.0])
        low = np.array([100.0, 100.0, 100.0, 89.0])
        out = simulate(close, high, low, np.zeros(4, dtype=int), 10_000.0,
                       risk=RiskModel(take_profit_pct=0.05), open_=close,
                       short_signals=np.array([1, 0, 0, 0]))
        trade = out["trades"][0]
        assert trade["exit_reason"] == "take_profit"
        assert trade["exit_price"] < trade["entry_price"]

    @pytest.mark.unit
    def test_stop_still_wins_over_target_in_the_same_candle(self):
        """La convención conservadora importa MÁS en un corto: su pérdida no
        tiene tope, así que suponer lo favorable es más caro."""
        close = np.array([100.0, 100.0, 100.0, 100.0])
        high = np.array([100.0, 100.0, 100.0, 110.0])
        low = np.array([100.0, 100.0, 100.0, 90.0])
        out = simulate(close, high, low, np.zeros(4, dtype=int), 10_000.0,
                       risk=RiskModel(stop_loss_pct=0.05, take_profit_pct=0.05),
                       open_=close, short_signals=np.array([1, 0, 0, 0]))
        assert out["trades"][0]["exit_reason"] == "stop_loss"

    @pytest.mark.unit
    def test_the_trailing_of_a_short_follows_the_LOW(self):
        """El «agua favorable» de un corto es el mínimo alcanzado, no el máximo."""
        close = np.array([100.0, 100.0, 90.0, 90.0, 95.0])
        high = np.array([100.0, 100.0, 100.0, 91.0, 95.0])
        low = np.array([100.0, 100.0, 89.0, 89.0, 90.0])
        out = simulate(close, high, low, np.zeros(5, dtype=int), 10_000.0,
                       risk=RiskModel(trailing_stop_pct=0.03), open_=close,
                       short_signals=np.array([1, 0, 0, 0, 0]))
        trade = out["trades"][0]
        assert trade["exit_reason"] == "trailing_stop"
        # Salta a ~89 × 1,03 ≈ 91,7, no al 3 % del máximo.
        assert trade["exit_price"] == pytest.approx(91.67, abs=0.5)

    @pytest.mark.unit
    def test_the_atr_stop_of_a_short_is_above_the_entry(self):
        close = _flat(4)
        high = np.array([100.0, 100.0, 100.0, 104.0])
        out = simulate(close, high, close, np.zeros(4, dtype=int), 10_000.0,
                       risk=RiskModel(atr_stop_mult=3.0), atr=np.full(4, 1.0),
                       open_=close, short_signals=np.array([1, 0, 0, 0]))
        assert out["trades"][0]["exit_reason"] == "atr_stop"
        assert out["trades"][0]["exit_price"] == pytest.approx(103.0)


class TestFundingSign:

    @pytest.mark.unit
    def test_a_positive_rate_is_INCOME_for_a_short(self):
        """«Los largos pagan a los cortos». El mismo número que es coste en un
        lado es ingreso en el otro."""
        close = _flat(8)
        out = simulate(close, close, close, np.zeros(8, dtype=int), 10_000.0,
                       open_=close, funding=np.full(8, 0.001),
                       short_signals=np.array([1, 0, 0, 0, 0, 0, -1, 0]))
        assert out["total_funding"] < 0        # negativo = cobrado, no pagado
        assert out["trades"][0]["pnl_pct"] > 0

    @pytest.mark.unit
    def test_the_same_rate_is_a_cost_for_a_long(self):
        close = _flat(8)
        out = simulate(close, close, close, np.array([1, 0, 0, 0, 0, 0, -1, 0]),
                       10_000.0, open_=close, funding=np.full(8, 0.001))
        assert out["total_funding"] > 0

    @pytest.mark.unit
    def test_a_negative_rate_flips_both_sides(self):
        close = _flat(8)
        short = simulate(close, close, close, np.zeros(8, dtype=int), 10_000.0,
                         open_=close, funding=np.full(8, -0.001),
                         short_signals=np.array([1, 0, 0, 0, 0, 0, -1, 0]))
        assert short["total_funding"] > 0      # ahora el corto paga


class TestOnePositionAtATime:

    @pytest.mark.unit
    def test_a_short_signal_is_ignored_while_a_long_is_open(self):
        """Permitir ambos lados a la vez sería una cartera, no una estrategia, y
        exigiría un modelo de margen que este motor no tiene."""
        close = _flat(6)
        out = simulate(close, close, close, np.array([1, 0, 0, 0, 0, 0]), 10_000.0,
                       open_=close, short_signals=np.array([0, 0, 1, 0, 0, 0]))
        assert len(out["trades"]) <= 1
        assert all(t["side"] == "long" for t in out["trades"])

    @pytest.mark.unit
    def test_closing_wins_over_opening_the_other_side_in_the_same_candle(self):
        """Dar la vuelta a la posición en una vela exigiría dos rellenos al mismo
        precio, que es el optimismo que el relleno desplazado evita."""
        close = _flat(6)
        out = simulate(close, close, close, np.array([1, 0, -1, 0, 0, 0]), 10_000.0,
                       open_=close, short_signals=np.array([0, 0, 1, 0, 0, 0]))
        # Cierra el largo; el corto solo podría abrirse en una vela posterior.
        assert out["trades"][0]["side"] == "long"

    @pytest.mark.unit
    def test_a_short_can_open_after_the_long_closes(self):
        close = _flat(8)
        out = simulate(close, close, close, np.array([1, 0, -1, 0, 0, 0, 0, 0]),
                       10_000.0, open_=close,
                       short_signals=np.array([0, 0, 0, 0, 1, 0, -1, 0]))
        sides = [t["side"] for t in out["trades"]]
        assert sides == ["long", "short"]


class TestBackwardCompatibility:

    @pytest.mark.unit
    def test_without_short_signals_nothing_changes(self):
        """Garantía que sostiene todo lo ya construido: el motor long-only debe
        comportarse exactamente igual que antes de existir los cortos."""
        rng = np.random.default_rng(3)
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 200)))
        signals = np.where(np.arange(200) % 20 == 0, 1,
                           np.where(np.arange(200) % 20 == 9, -1, 0))
        risk = RiskModel(stop_loss_pct=0.05, take_profit_pct=0.1)

        a = simulate(close, close * 1.01, close * 0.99, signals, 10_000.0,
                     risk=risk, open_=close)
        b = simulate(close, close * 1.01, close * 0.99, signals, 10_000.0,
                     risk=risk, open_=close, short_signals=np.zeros(200, dtype=int))
        assert a["trades"] == b["trades"]
        assert a["final_capital"] == pytest.approx(b["final_capital"])

    @pytest.mark.unit
    def test_long_trades_declare_their_side(self):
        close = _flat(6)
        out = simulate(close, close, close, np.array([1, 0, -1, 0, 0, 0]),
                       10_000.0, open_=close)
        assert out["trades"][0]["side"] == "long"
