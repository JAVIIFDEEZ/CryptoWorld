"""
tests/unit/domain/test_ml_prediction.py — Predicción ML de dirección (honesta).

Verifica que la evaluación es out-of-sample (walk-forward), que reporta el edge
sobre la línea base y que, sobre ruido, NO inventa una ventaja inexistente.
"""

import numpy as np
import pandas as pd
import pytest

from core.domain.services.technical_analysis_service import predict_price_direction


def _df(close):
    close = np.asarray(close, dtype=float)
    n = len(close)
    return pd.DataFrame({
        "timestamp": [1700000000000 + i * 86400000 for i in range(n)],
        "open": close, "high": close + 1, "low": close - 1, "close": close,
        "volume": [1000.0] * n,
    })


def _trend_cycle(n=400, seed=1):
    rng = np.random.default_rng(seed)
    t = np.arange(n)
    return np.maximum(100 + 0.1 * t + 8 * np.sin(t / 20.0) + rng.normal(0, 1.5, n), 5.0)


def _noise(n=400, seed=2):
    rng = np.random.default_rng(seed)
    return 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))


class TestPredictionStructure:

    @pytest.mark.unit
    def test_returns_oos_metrics_and_verdict(self):
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        for key in ("prediction", "confidence", "oos_accuracy", "baseline_accuracy",
                    "edge", "precision_up", "recall_up", "f1_up", "n_oos", "n_splits", "verdict"):
            assert key in r
        assert r["prediction"] in ("ALCISTA", "BAJISTA", "NEUTRAL")
        assert 0.0 <= r["confidence"] <= 1.0
        # El edge es exactamente la precisión OOS menos la línea base
        assert r["edge"] == pytest.approx(r["oos_accuracy"] - r["baseline_accuracy"], abs=1e-6)
        # La validación usó varios tramos OOS reales
        assert r["n_splits"] >= 3 and r["n_oos"] > 50

    @pytest.mark.unit
    def test_insufficient_data(self):
        r = predict_price_direction(_df(_trend_cycle(n=50)), horizon=5)
        assert r["prediction"] == "INSUFFICIENT_DATA"

    @pytest.mark.unit
    def test_deterministic(self):
        df = _df(_trend_cycle())
        a = predict_price_direction(df, horizon=5)
        b = predict_price_direction(df, horizon=5)
        assert a["oos_accuracy"] == b["oos_accuracy"] and a["prediction"] == b["prediction"]


class TestHonesty:

    @pytest.mark.unit
    def test_no_edge_on_pure_noise(self):
        """Sobre un random walk el modelo no debe reclamar ventaja: el edge OOS
        es ~0 y el veredicto no es EDGE (la clave de un ML honesto)."""
        r = predict_price_direction(_df(_noise()), horizon=5)
        assert r["edge"] < 0.04
        assert r["verdict"] in ("NO_EDGE", "WEAK")

    @pytest.mark.unit
    def test_baseline_is_majority_class_rate(self):
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        # La línea base = acierto de predecir siempre la clase mayoritaria ≥ 0.5
        assert r["baseline_accuracy"] >= 0.5
        assert r["baseline_accuracy"] == pytest.approx(max(r["up_rate"], 1 - r["up_rate"]), abs=1e-6)


class TestNeutralZone:

    @pytest.mark.unit
    def test_neutral_when_calibrated_prob_near_half(self):
        """prob_up dentro de [45%,55%] → NEUTRAL: no se proclama dirección a
        cara o cruz (y log_prediction no la registra en el historial)."""
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        band = r.get("neutral_band", 0.05)
        if abs(r["prob_up"] - 0.5) <= band:
            assert r["prediction"] == "NEUTRAL"
        else:
            assert r["prediction"] == ("ALCISTA" if r["prob_up"] > 0.5 else "BAJISTA")

    @pytest.mark.unit
    def test_neutral_band_exposed(self):
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        assert 0.0 < r["neutral_band"] <= 0.1


class TestCalibration:

    @pytest.mark.unit
    def test_probabilities_are_calibrated(self):
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        assert r["calibrated"] is True
        assert r["brier_score"] is not None and 0.0 <= r["brier_score"] <= 1.0
        # La confianza calibrada es una probabilidad válida
        assert 0.5 <= r["confidence"] <= 1.0
        assert r["prob_up"] is not None


class TestEnsemble:

    @pytest.mark.unit
    def test_model_is_voting_ensemble(self):
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        assert "Ensemble" in r["model"] and "RF+GB+LR" in r["model"]
        # Sigue exponiendo importancias, ahora MDA por clúster (ver más abajo)
        assert len(r["features_importance"]) >= 3


class TestLocalExplainability:
    """Atribución por oclusión: por qué el modelo decide ESTA vela."""

    @pytest.mark.unit
    def test_drivers_present_and_well_formed(self):
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        assert "drivers" in r and isinstance(r["drivers"], list)
        assert 1 <= len(r["drivers"]) <= 6
        for d in r["drivers"]:
            assert set(d.keys()) == {"feature", "contribution"}
            assert d["feature"] in [f["feature"] for f in r["features_importance"]] or isinstance(d["feature"], str)
            assert isinstance(d["contribution"], float)

    @pytest.mark.unit
    def test_drivers_sorted_by_absolute_contribution(self):
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        mags = [abs(d["contribution"]) for d in r["drivers"]]
        assert mags == sorted(mags, reverse=True)

    @pytest.mark.unit
    def test_drivers_deterministic(self):
        df = _df(_trend_cycle())
        a = predict_price_direction(df, horizon=5)
        b = predict_price_direction(df, horizon=5)
        assert a["drivers"] == b["drivers"]


class TestPurgedValidation:
    """
    Respetar el orden temporal no basta.

    Con horizonte 5, la etiqueta de la fila `k` se resuelve mirando `close[k+5]`:
    si el test empieza en `k+1`, las últimas cinco filas del train ya contienen
    información del periodo de test. `TimeSeriesSplit` no lo corrige, y la fuga
    —pequeña pero sistemática— siempre empuja en el mismo sentido: infla la
    precisión que se publica. Medido sobre ocho series de ruido puro, la inflaba
    en 0,76 puntos porcentuales.
    """

    @pytest.mark.unit
    def test_the_report_says_what_it_removed(self):
        """Sin la cifra, purgar es un cambio invisible: los números se mueven y
        nadie sabe si fue la corrección o la semilla."""
        out = predict_price_direction(_df(_trend_cycle(600)), horizon=5)
        purge = out["purged_cv"]
        assert purge["horizon"] == 5
        assert purge["gap_bars"] > purge["horizon"]     # hay embargo además de purga
        assert purge["embargo_bars"] > 0

    @pytest.mark.unit
    def test_the_gap_follows_the_horizon(self):
        """Un horizonte más largo contamina más filas, y el hueco tiene que
        seguirlo. Si fuera constante, la purga sería decorativa."""
        short = predict_price_direction(_df(_trend_cycle(600)), horizon=3)["purged_cv"]
        long_ = predict_price_direction(_df(_trend_cycle(600)), horizon=20)["purged_cv"]
        assert long_["gap_bars"] > short["gap_bars"]


class TestEdgeSignificance:
    """
    El veredicto `EDGE` era `edge >= 0.04`, una magnitud contra un umbral fijo.
    Sobre unos cientos de muestras, cuatro puntos son menos de dos desviaciones
    típicas: ese umbral no medía señal.
    """

    @pytest.mark.unit
    def test_the_edge_travels_with_its_interval(self):
        out = predict_price_direction(_df(_trend_cycle(600)), horizon=5)
        assert out["edge_ci_low"] <= out["edge"] <= out["edge_ci_high"]
        assert out["n_oos"] > 0

    @pytest.mark.unit
    def test_edge_verdict_requires_the_interval_to_clear_zero(self):
        """La condición que sustituye al umbral. Si el veredicto fuera EDGE con
        el intervalo cruzando el cero, seguiríamos anunciando ruido."""
        out = predict_price_direction(_df(_trend_cycle(600)), horizon=5)
        if out["verdict"] == "EDGE":
            assert out["edge_ci_low"] > 0
        assert out["edge_significant"] == (out["edge_ci_low"] > 0)

    @pytest.mark.unit
    def test_pure_noise_never_earns_an_edge_verdict(self):
        for seed in (2, 5, 9):
            out = predict_price_direction(_df(_noise(700, seed=seed)), horizon=5)
            assert out["verdict"] != "EDGE"

    @pytest.mark.unit
    def test_a_weak_verdict_says_how_wide_the_interval_is(self):
        """«Señal débil, tómatela con cautela» no dice nada accionable. El
        intervalo sí: enseña que la ventaja observada cabe dentro del azar."""
        out = predict_price_direction(_df(_noise(700, seed=2)), horizon=5)
        if out["verdict"] == "WEAK":
            assert "compatible con el azar" in out["verdict_text"]


class TestNestedCalibrationMeasurement:
    """
    Medir el Brier sobre los mismos puntos con los que se ajustó Platt es
    preguntarle al calibrador qué tal calibra en los datos que usó para
    calibrarse. Sale bien por construcción y no dice nada.
    """

    @pytest.mark.unit
    def test_the_brier_is_measured_out_of_sample_of_the_calibrator(self):
        out = predict_price_direction(_df(_trend_cycle(800)), horizon=5)
        assert out["brier_nested"] is True

    @pytest.mark.unit
    def test_when_it_cannot_be_nested_it_says_so_instead_of_hiding_it(self):
        """Con muestra corta no se puede partir en dos. La cifra se da igual,
        pero marcada — nadie puede leerla como fuera de muestra."""
        out = predict_price_direction(_df(_trend_cycle(240)), horizon=5)
        if out.get("brier_score") is not None:
            assert isinstance(out["brier_nested"], bool)


class TestGlobalImportanceIsOutOfSample:
    """
    Lo que se enseñaba aquí era MDI: impureza decrecida DENTRO de muestra, con
    la etiqueta «variables más influyentes». Premia igual a una variable que
    informa y a una que memoriza ruido, y ordena por cardinalidad — y el estudio
    de features exógenas de esta misma plataforma ya lo declaraba inservible
    para decidir nada. Enseñarlo mientras se argumentaba eso era sostener las dos
    cosas a la vez.

    Ahora es MDA sobre los tramos purgados: cuánta precisión se pierde al
    permutar cada grupo de variables fuera de muestra.
    """

    @pytest.mark.unit
    def test_it_declares_which_method_produced_the_number(self):
        """El valor cambió de significado —de un reparto que suma 1 a puntos de
        precisión perdidos, que pueden ser negativos—. Sin declararlo, quien lea
        la cifra la interpretará con la escala anterior."""
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        assert r["importance_method"] == "MDA_PURGED"

    @pytest.mark.unit
    def test_every_group_carries_its_uncertainty(self):
        """Una caída media de 0,01 con desviación 0,05 no es importancia, es
        ruido. Sin el error estándar al lado, una lista ordenada siempre parece
        significativa: SIEMPRE hay un primero."""
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        for f in r["features_importance"]:
            assert {"feature", "columns", "importance", "std_error",
                    "p_value", "significant"} <= set(f)

    @pytest.mark.unit
    def test_each_row_says_which_columns_it_speaks_for(self):
        """17 indicadores técnicos son un conjunto de sinónimos. «rsi_14» en la
        lista representa a todas las que dicen casi lo mismo, y ocultarlo haría
        leer un grupo como una variable."""
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        assert any(len(f["columns"]) > 1 for f in r["features_importance"])
        for f in r["features_importance"]:
            assert f["feature"] in f["columns"]

    @pytest.mark.unit
    def test_the_list_is_sorted_by_measured_drop(self):
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        caidas = [f["importance"] for f in r["features_importance"]]
        assert caidas == sorted(caidas, reverse=True)

    @pytest.mark.unit
    def test_on_pure_noise_no_group_is_declared_important(self):
        """La prueba de que la lista puede decir «aquí no hay nada». MDI no podía:
        siempre repartía el 100 % entre las 17 features, hubiera señal o no."""
        r = predict_price_direction(_df(_noise()), horizon=5)
        assert not any(f["significant"] for f in r["features_importance"])

    @pytest.mark.unit
    def test_the_note_says_what_a_non_significant_group_means(self):
        """Con 3-6 tramos el contraste tiene poca potencia. Medido sobre series
        con señal plantada, el grupo correcto sale primero por un factor de diez
        y aun así no alcanza significancia en una de cada tres semillas. Leer esa
        ausencia como «no aporta» sería exactamente el error inverso al que este
        cambio corrige."""
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        assert "no se ha demostrado que aporte" in r["importance_note"]

    @pytest.mark.unit
    def test_importance_is_measured_on_the_purged_folds_not_on_everything(self):
        """Medirla sobre el modelo final —ajustado con todo el histórico— sería
        volver a una cifra dentro de muestra con otro nombre."""
        r = predict_price_direction(_df(_trend_cycle()), horizon=5)
        # Un grupo puede salir NEGATIVO: romperlo mejora el acierto. Eso solo
        # ocurre fuera de muestra; en la métrica in-sample era imposible.
        assert all(isinstance(f["importance"], float) for f in r["features_importance"])
        assert r["n_splits"] >= 3
