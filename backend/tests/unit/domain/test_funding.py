"""
test_funding.py — El coste de mantener abierto un perpetuo.

Un backtest de perpetuos sin funding no mide la estrategia: mide una versión de
ella que nadie puede operar. Y el error no es constante — crece con el tiempo
que la posición permanece abierta, que es justo lo que distingue a una
estrategia de tendencia de una de scalping.

Lo que se fija aquí:
  · varias liquidaciones dentro de una misma vela se SUMAN;
  · el funding solo se cobra con la posición abierta;
  · cuesta más cuanto más dura el trade;
  · un histórico sin la columna se comporta exactamente como antes.
"""

import numpy as np
import pytest

from core.domain.services import funding
from core.domain.services.backtest_execution import simulate

DAY_MS = 86_400_000
HOUR8_MS = 8 * 3_600_000


class TestFundingPerBar:

    @pytest.mark.unit
    def test_three_settlements_in_a_daily_candle_are_added(self):
        """En una vela diaria caben tres liquidaciones de 8 horas. Imputar solo
        una subestimaría el coste en dos tercios."""
        bars = [0, DAY_MS, 2 * DAY_MS]
        records = [(0, 0.0001), (HOUR8_MS, 0.0001), (2 * HOUR8_MS, 0.0001)]
        out = funding.funding_per_bar(records, bars, DAY_MS)
        assert out[0] == pytest.approx(0.0003)
        assert out[1] == 0.0 and out[2] == 0.0

    @pytest.mark.unit
    def test_settlement_lands_in_the_candle_that_contains_it(self):
        bars = [0, DAY_MS, 2 * DAY_MS]
        out = funding.funding_per_bar([(DAY_MS + 100, 0.0005)], bars, DAY_MS)
        assert out[1] == pytest.approx(0.0005)

    @pytest.mark.unit
    def test_settlements_outside_the_history_are_dropped(self):
        bars = [DAY_MS, 2 * DAY_MS]
        out = funding.funding_per_bar([(0, 0.01), (99 * DAY_MS, 0.01)], bars, DAY_MS)
        assert out.sum() == 0.0

    @pytest.mark.unit
    def test_a_gap_in_the_history_does_not_absorb_a_payment(self):
        """Si entre dos velas falta histórico, el pago de ese hueco no pertenece
        a la vela anterior: cobrarlo ahí inventaría un coste donde no lo hubo."""
        bars = [0, 10 * DAY_MS]
        out = funding.funding_per_bar([(5 * DAY_MS, 0.01)], bars, DAY_MS)
        assert out.sum() == 0.0

    @pytest.mark.unit
    def test_sign_is_respected_so_a_negative_rate_pays_the_long(self):
        """El signo importa: cobrar cuando toca cobrar es parte de medir bien.
        Tomar valor absoluto convertiría un ingreso en un coste."""
        out = funding.funding_per_bar([(0, -0.0004)], [0], DAY_MS)
        assert out[0] < 0


class TestFundingInTheEngine:

    @staticmethod
    def _run(n_bars_held: int, rate: float = 0.0003):
        """Un trade que dura `n_bars_held` velas con funding constante."""
        n = n_bars_held + 3
        close = np.full(n, 100.0)
        signals = np.zeros(n, dtype=int)
        signals[0] = 1
        signals[n_bars_held + 1] = -1
        return simulate(close, close, close, signals, 10_000.0, open_=close,
                        funding=np.full(n, rate))

    @pytest.mark.unit
    def test_funding_is_charged_while_the_position_is_open(self):
        out = self._run(5)
        assert out["total_funding"] > 0
        assert out["final_capital"] < 10_000.0

    @pytest.mark.unit
    def test_a_longer_trade_pays_more(self):
        """Es la propiedad que hace del funding un coste distinto de la
        comisión: escala con el tiempo en mercado, no con el nº de operaciones."""
        short = self._run(3)["total_funding"]
        long_ = self._run(30)["total_funding"]
        assert long_ > short * 5

    @pytest.mark.unit
    def test_a_negative_rate_is_income_not_cost(self):
        out = self._run(10, rate=-0.0003)
        assert out["total_funding"] < 0
        assert out["final_capital"] > 10_000.0

    @pytest.mark.unit
    def test_the_trade_pnl_includes_the_funding_it_paid(self):
        """El Monte Carlo y la tasa de acierto se alimentan de `pnl_pct`. Si el
        funding quedara fuera, medirían una operación más barata que la real."""
        free = self._run(20, rate=0.0)["trades"][0]
        charged = self._run(20, rate=0.0005)["trades"][0]
        assert charged["funding_paid"] > 0
        assert charged["pnl_pct"] < free["pnl_pct"]

    @pytest.mark.unit
    def test_funding_of_one_trade_does_not_leak_into_the_next(self):
        """El acumulador es por operación: arrastrarlo cobraría dos veces."""
        close = np.full(20, 100.0)
        signals = np.zeros(20, dtype=int)
        signals[0], signals[4] = 1, -1        # trade corto
        signals[8], signals[16] = 1, -1       # trade largo
        out = simulate(close, close, close, signals, 10_000.0, open_=close,
                       funding=np.full(20, 0.0002))
        first, second = out["trades"][0], out["trades"][1]
        assert second["funding_paid"] > first["funding_paid"]
        assert first["funding_paid"] + second["funding_paid"] == pytest.approx(
            out["total_funding"])

    @pytest.mark.unit
    def test_nothing_is_charged_while_flat(self):
        """Sin posición no hay nada que financiar. Cobrar igual sería un
        impuesto sobre estar en liquidez, que no existe."""
        close = np.full(20, 100.0)
        out = simulate(close, close, close, np.zeros(20, dtype=int), 10_000.0,
                       open_=close, funding=np.full(20, 0.001))
        assert out["total_funding"] == 0.0
        assert out["final_capital"] == pytest.approx(10_000.0)

    @pytest.mark.unit
    def test_absent_funding_reproduces_the_previous_engine(self):
        """Compatibilidad: un histórico sin la columna debe dar exactamente lo
        mismo que antes de que existiera este coste."""
        rng = np.random.default_rng(2)
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 100)))
        signals = np.where(np.arange(100) % 10 == 0, 1,
                           np.where(np.arange(100) % 10 == 5, -1, 0))
        a = simulate(close, close, close, signals, 10_000.0, open_=close)
        b = simulate(close, close, close, signals, 10_000.0, open_=close,
                     funding=np.zeros(100))
        assert a["final_capital"] == pytest.approx(b["final_capital"])
        assert a["total_funding"] == 0.0


class TestFundingOnTheShortSide:
    """
    En un perpetuo, una tasa positiva significa que los LARGOS pagan a los
    cortos. La misma cifra es coste en un lado e ingreso en el otro.

    No es un detalle contable: es una asimetría económica real que inclina el
    atractivo relativo de los dos lados. Aplicar el funding con el mismo signo a
    ambos —el error fácil— premiaría o castigaría a uno sin motivo, y el
    generador acabaría prefiriendo un lado por una razón inventada.
    """

    @staticmethod
    def _run(short: bool, rate: float = 0.0003, n_bars_held: int = 10):
        n = n_bars_held + 3
        close = np.full(n, 100.0)
        opens = np.zeros(n, dtype=int)
        opens[0] = 1
        opens[n_bars_held + 1] = -1
        blank = np.zeros(n, dtype=int)
        return simulate(close, close, close, blank if short else opens, 10_000.0,
                        open_=close, funding=np.full(n, rate),
                        short_signals=opens if short else None)

    @pytest.mark.unit
    def test_a_positive_rate_is_a_cost_for_the_long_and_income_for_the_short(self):
        assert self._run(short=False)["total_funding"] > 0
        assert self._run(short=True)["total_funding"] < 0

    @pytest.mark.unit
    def test_a_negative_rate_flips_both_sides(self):
        """Los regímenes de funding negativo existen (mercado bajista con exceso
        de cortos) y ahí el que cobra es el largo."""
        assert self._run(short=False, rate=-0.0003)["total_funding"] < 0
        assert self._run(short=True, rate=-0.0003)["total_funding"] > 0

    @pytest.mark.unit
    def test_the_two_sides_pay_the_same_magnitude(self):
        """Sobre el mismo nocional y el mismo tiempo en mercado, lo que uno paga
        es lo que el otro cobra."""
        paid = self._run(short=False)["total_funding"]
        received = self._run(short=True)["total_funding"]
        assert abs(paid + received) < abs(paid) * 0.05

    @pytest.mark.unit
    def test_the_short_trade_pnl_reflects_the_funding_it_collected(self):
        """Si el cobro no entrase en `pnl_pct`, el Monte Carlo y la tasa de
        acierto —que se alimentan de esa cifra— medirían una operación más pobre
        que la real."""
        collected = self._run(short=True)["trades"][0]
        assert collected["funding_paid"] < 0
        paid = self._run(short=True, rate=-0.0003)["trades"][0]
        assert paid["funding_paid"] > 0
        assert collected["pnl_pct"] > paid["pnl_pct"]


class TestReporting:

    @pytest.mark.unit
    def test_annualizes_at_three_settlements_a_day(self):
        """1 bp por liquidación × 3 al día × 365 = 1095 bps al año. Es la cifra
        que hace comparable el funding con la comisión."""
        assert funding.annualized_cost_bps([0.0001] * 10) == pytest.approx(1095.0)

    @pytest.mark.unit
    def test_describe_says_who_paid_and_how_much(self):
        out = funding.describe([0.0002] * 8 + [-0.0001] * 2)
        assert out["pct_paid_by_longs"] == 80.0
        assert out["annualized_cost_bps"] > 0
        assert "%" in out["note"]

    @pytest.mark.unit
    def test_describe_calls_a_negative_regime_income(self):
        out = funding.describe([-0.0003] * 10)
        assert out["annualized_cost_bps"] < 0
        assert "ingreso" in out["note"]

    @pytest.mark.unit
    def test_empty_history_is_declared_not_assumed_zero(self):
        assert funding.describe([])["n"] == 0
