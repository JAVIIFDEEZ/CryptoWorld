"""
test_block_sampling.py — Buscar sobre años sin pagar años de cómputo.

El coste del GA es lineal en velas (medido: 584 ≈ 4 min de evolución exhaustiva,
8000 ≈ 37 min). Usar tres años de gráficos horarios llevaría la búsqueda a más de
dos horas; sin tres años, lo que se encuentre estará ajustado a un solo régimen.

La salida es separar dos preguntas que se respondían con el mismo cálculo: el
fitness solo tiene que **ordenar** genomas, y ordenar no exige medirlo todo. El
veredicto sigue saliendo del gating sobre el histórico completo.

Lo que se fija aquí son las tres reglas sin las cuales el atajo dejaría de ser
válido:

  1. cada bloque arrastra su calentamiento, y ese tramo NO puntúa;
  2. los bloques cubren todo el histórico, no un trozo;
  3. los precios de bloques distintos JAMÁS se concatenan — entre uno y otro
     puede haber meses, y unirlos inventaría el movimiento más grande de la
     serie justo en la costura.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services import block_sampling as bs


def _df(n=6000, seed=5):
    rng = np.random.default_rng(seed)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    return pd.DataFrame({
        "timestamp": [1_600_000_000_000 + i * 3_600_000 for i in range(n)],
        "open": close, "high": close * 1.005, "low": close * 0.995,
        "close": close, "volume": np.ones(n) * 1000,
    })


class TestPlanning:

    @pytest.mark.unit
    def test_blocks_are_spread_across_the_whole_history(self):
        """Un tramo contiguo haría que el GA optimizara para un solo régimen —
        exactamente el sesgo que se quiere evitar, solo que deliberado."""
        blocks = bs.plan_blocks(12000, n_blocks=6, warmup=200, target_scored=1800)
        assert len(blocks) >= 4
        assert bs.coverage_ratio(blocks, 12000) > 0.8

    @pytest.mark.unit
    def test_the_sample_is_a_small_fraction_of_the_history(self):
        """Es el punto: desacoplar el coste de la longitud de la serie."""
        blocks = bs.plan_blocks(12000, n_blocks=6, warmup=200, target_scored=1800)
        assert bs.sampled_ratio(blocks, 12000) < 0.25

    @pytest.mark.unit
    def test_every_block_carries_its_warmup(self):
        """Sin calentamiento, el arranque de cada bloque mediría cómo se ceba una
        media de 200 velas en lugar de medir la estrategia."""
        blocks = bs.plan_blocks(12000, n_blocks=6, warmup=200, target_scored=1800)
        assert all(b.score_start - b.warmup_start > 0 for b in blocks[1:])

    @pytest.mark.unit
    def test_the_first_block_does_not_pretend_to_have_a_past(self):
        """No hay velas antes de la primera: se le cede su propio arranque como
        calentamiento en vez de fingir que existe."""
        blocks = bs.plan_blocks(12000, n_blocks=6, warmup=200, target_scored=1800)
        assert blocks[0].warmup_start >= 0
        assert blocks[0].score_start >= 200

    @pytest.mark.unit
    def test_blocks_never_overlap(self):
        """Dos bloques que compartan velas puntuarían dos veces el mismo tramo y
        le darían un peso doble sin motivo."""
        blocks = bs.plan_blocks(12000, n_blocks=6, warmup=200, target_scored=1800)
        for a, b in zip(blocks, blocks[1:]):
            assert a.end <= b.score_start

    @pytest.mark.unit
    def test_the_plan_is_deterministic(self):
        """La muestra debe ser la MISMA para todos los genomas de la ejecución:
        si cambiara, se compararían estrategias medidas sobre datos distintos y
        el ranking sería ruido con aspecto de selección."""
        a = bs.plan_blocks(12000, n_blocks=6, warmup=200, target_scored=1800)
        b = bs.plan_blocks(12000, n_blocks=6, warmup=200, target_scored=1800)
        assert a == b

    @pytest.mark.unit
    def test_a_short_history_degrades_to_using_it_whole(self):
        """Es lo que el motor ya hacía antes de existir este módulo, y sigue
        siendo lo correcto cuando no hay de dónde muestrear."""
        blocks = bs.plan_blocks(800, n_blocks=6, warmup=200, target_scored=1800)
        assert len(blocks) == 1
        assert blocks[0].end == 800

    @pytest.mark.unit
    def test_an_empty_history_yields_no_blocks(self):
        assert bs.plan_blocks(0) == []


class TestEvaluation:

    @pytest.mark.unit
    def test_prices_of_different_blocks_are_never_concatenated(self):
        """La regla que sostiene la validez: entre el final de un bloque y el
        principio del siguiente puede haber meses. Unir los precios crearía un
        salto ficticio que el backtest leería como el mayor movimiento de la
        serie.

        Se comprueba viendo que cada bloque se backtestea POR SEPARADO: la
        función recibe tantas llamadas como bloques, cada una con su tramo.
        """
        df = _df(12000)
        blocks = bs.plan_blocks(12000, n_blocks=6, warmup=200, target_scored=1800)
        seen = []

        def fake_backtest(sub):
            seen.append((len(sub), float(sub["close"].iloc[0])))
            return {"bar_returns": [0.001] * len(sub), "trades": []}

        bs.evaluate_blocks(df, blocks, fake_backtest)
        assert len(seen) == len(blocks)
        # Cada llamada recibe un tramo distinto del histórico.
        assert len({s[1] for s in seen}) == len(blocks)

    @pytest.mark.unit
    def test_warmup_returns_do_not_score(self):
        df = _df(12000)
        blocks = bs.plan_blocks(12000, n_blocks=6, warmup=200, target_scored=1800)

        def fake_backtest(sub):
            return {"bar_returns": [0.001] * len(sub), "trades": []}

        agg = bs.evaluate_blocks(df, blocks, fake_backtest)
        assert agg["scored_bars"] == sum(b.scored_bars for b in blocks)
        assert agg["scored_bars"] < sum(b.total_bars for b in blocks)

    @pytest.mark.unit
    def test_trades_opened_during_the_warmup_are_not_counted(self):
        """El calentamiento existe para que los indicadores lleguen cebados, no
        para aportar resultados."""
        df = _df(12000)
        blocks = bs.plan_blocks(12000, n_blocks=6, warmup=200, target_scored=1800)

        def fake_backtest(sub):
            return {"bar_returns": [0.0] * len(sub),
                    "trades": [{"entry_index": 5, "pnl_pct": 1.0},      # calentamiento
                               {"entry_index": 250, "pnl_pct": 1.0}]}   # puntuable

        agg = bs.evaluate_blocks(df, blocks, fake_backtest)
        # Solo la segunda de cada bloque (el primero no tiene calentamiento previo).
        assert agg["total_trades"] <= len(blocks) + 1

    @pytest.mark.unit
    def test_a_single_block_behaves_like_the_plain_history(self):
        df = _df(800)
        blocks = bs.plan_blocks(800, n_blocks=6, warmup=200, target_scored=1800)

        def fake_backtest(sub):
            return {"bar_returns": [0.001] * len(sub), "trades": []}

        agg = bs.evaluate_blocks(df, blocks, fake_backtest)
        assert agg["n_blocks"] == 1
        assert agg["scored_bars"] > 500


class TestReporting:

    @pytest.mark.unit
    def test_the_description_states_what_was_sampled(self):
        """Un fitness de muestra y uno de histórico completo NO son comparables;
        callar de dónde sale invitaría a compararlos."""
        blocks = bs.plan_blocks(12000, n_blocks=6, warmup=200, target_scored=1800)
        out = bs.describe(blocks, 12000)
        assert out["n_blocks"] == len(blocks)
        assert out["sampled_pct"] < 25
        assert out["coverage_pct"] > 80
        assert "ORDENAR" in out["note"]

    @pytest.mark.unit
    def test_coverage_and_sampling_are_different_questions(self):
        """Una muestra que puntúa el 15 % pero solo toca los primeros seis meses
        no vale; una que puntúa el 15 % repartido por tres años, sí."""
        blocks = bs.plan_blocks(12000, n_blocks=6, warmup=200, target_scored=1800)
        assert bs.coverage_ratio(blocks, 12000) > bs.sampled_ratio(blocks, 12000)

    @pytest.mark.unit
    def test_no_blocks_is_described_not_crashed(self):
        assert bs.describe([], 1000)["n_blocks"] == 0
