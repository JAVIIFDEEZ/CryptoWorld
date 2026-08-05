"""
test_generation_power.py — Distinguir «no hay edge» de «no hay muestra».

El motor pedía **730 velas para todos los marcos** — un número elegido cuando
solo había gráficos diarios (730 = 2 años). En 1 h son 30 días, y cada tramo del
walk-forward cubría cinco días. Una estrategia que opera dos veces por semana
deja ahí **una operación por tramo**.

Con esa muestra, el motor corría 1477 evaluaciones, no aprobaba nada y lo
presentaba como «el mercado no ofrece un edge robusto». Eso es una atribución
falsa: no se descubrió nada sobre el mercado, se descubrió que faltaban datos.

Se fija aquí que el diagnóstico separe ambas causas, que hable en OPERACIONES
—que es la unidad que decide si un Sharpe significa algo— y que el número de
velas se pida por calendario y no por recuento.
"""

import pytest

from core.domain.services import generation_power as power


class TestSpan:

    @pytest.mark.unit
    def test_the_same_candle_count_means_very_different_histories(self):
        """El origen del problema, en una línea: 730 velas son dos años en
        diario y un mes en 1 h."""
        assert power.span_days(730, "1d") == pytest.approx(730)
        assert power.span_days(730, "1h") == pytest.approx(30.4, abs=0.1)

    @pytest.mark.unit
    def test_an_unknown_interval_does_not_crash(self):
        assert power.span_days(730, "3s") == 0.0


class TestAssessment:

    @pytest.mark.unit
    def test_the_users_exact_case_is_declared_inconclusive(self):
        """BTC 1 h, 730 velas, 4 tramos: el caso de la captura."""
        out = power.assess(candles=730, interval="1h", wf_splits=4,
                           evolution_candles=584, trades_observed=14)
        assert out["reliability"] == "insufficient"
        assert power.explains_empty_book(out)

    @pytest.mark.unit
    def test_it_reports_days_per_fold_not_just_bars(self):
        """116 velas suena razonable; cinco días no. La unidad importa."""
        out = power.assess(candles=730, interval="1h", wf_splits=4,
                           evolution_candles=584)
        assert out["bars_per_fold"] == 116
        assert out["days_per_fold"] == pytest.approx(4.8, abs=0.1)

    @pytest.mark.unit
    def test_too_few_trades_per_fold_is_the_binding_limit(self):
        """El Sharpe de un tramo con dos operaciones no es una medida ruidosa:
        no es una medida."""
        out = power.assess(candles=4000, interval="4h", wf_splits=4,
                           trades_observed=10)
        assert out["reliability"] == "insufficient"
        assert any("operaciones" in l for l in out["limits"])

    @pytest.mark.unit
    def test_a_long_history_with_plenty_of_trades_is_conclusive(self):
        out = power.assess(candles=1000, interval="1d", wf_splits=4,
                           trades_observed=200)
        assert out["reliability"] == "high"
        assert not power.explains_empty_book(out)

    @pytest.mark.unit
    def test_a_conclusive_run_says_the_verdict_is_about_the_market(self):
        out = power.assess(candles=1000, interval="1d", wf_splits=4,
                           trades_observed=200)
        assert "sobre el mercado" in out["note"]

    @pytest.mark.unit
    def test_an_inconclusive_run_refuses_to_blame_the_market(self):
        out = power.assess(candles=730, interval="1h", wf_splits=4,
                           trades_observed=14)
        assert "NO es concluyente" in out["note"]

    @pytest.mark.unit
    def test_a_short_history_alone_downgrades_to_low_not_insufficient(self):
        """Menos de seis meses no cubre un ciclo, pero con operaciones de sobra
        el veredicto sigue siendo orientable: `low`, no `insufficient`."""
        out = power.assess(candles=2000, interval="1h", wf_splits=4,
                           trades_observed=300)
        assert out["reliability"] == "low"

    @pytest.mark.unit
    def test_monte_carlo_needs_a_sequence_to_resample(self):
        """Con menos de 30 operaciones, el percentil 5 no distingue una
        estrategia mala de una con mala suerte."""
        out = power.assess(candles=1000, interval="1d", wf_splits=4,
                           trades_observed=25)
        assert out["reliability"] == "insufficient"
        assert any("Monte Carlo" in l for l in out["limits"])

    @pytest.mark.unit
    def test_without_trade_data_it_still_judges_the_geometry(self):
        """Sin operaciones observadas no puede hablar de tramos, pero el caso
        más común —marco corto con el límite de un marco largo— ya se detecta
        solo con las velas."""
        out = power.assess(candles=730, interval="1h", wf_splits=4)
        assert out["reliability"] == "insufficient"
        assert out["trades_per_fold"] is None


class TestRecommendedCandles:

    @pytest.mark.unit
    def test_the_request_scales_with_the_interval(self):
        """Pedir por calendario en vez de por recuento es lo que arregla la
        raíz: el mismo número de velas para todos los marcos era el bug."""
        assert power.recommended_candles("1h") > power.recommended_candles("1d")
        assert power.recommended_candles("1d") > power.recommended_candles("1w")

    @pytest.mark.unit
    def test_every_interval_now_covers_more_calendar_than_before(self):
        """Salvo el semanal, donde 730 velas ya eran 14 años y el recorte es
        deliberado: más allá de cierto punto el histórico antiguo describe otro
        mercado."""
        for interval in ("15m", "1h", "4h", "1d"):
            n = power.recommended_candles(interval)
            assert power.span_days(n, interval) > power.span_days(730, interval)

    @pytest.mark.unit
    def test_the_cap_bounds_the_compute_cost(self):
        """
        El coste del GA es lineal en velas —medido: 584 ≈ 4 min de evolución
        exhaustiva, 4000 ≈ 20 min, 8000 ≈ 37—, así que un objetivo sin tope
        convertiría cada ejecución en una espera inaceptable.

        El tope se subió mientras se creía que la búsqueda en dos fases
        desacoplaba el coste; esa comprobación salió negativa y el tope volvió a
        donde el coste manda.
        """
        assert power.recommended_candles("1m") <= 4000

    @pytest.mark.unit
    def test_the_floor_keeps_long_intervals_runnable(self):
        """En semanal, 1000 días serían 143 velas: por debajo del mínimo que el
        propio generador exige."""
        assert power.recommended_candles("1w") >= 300

    @pytest.mark.unit
    def test_an_unknown_interval_falls_back_to_the_old_default(self):
        assert power.recommended_candles("3s") == 730
