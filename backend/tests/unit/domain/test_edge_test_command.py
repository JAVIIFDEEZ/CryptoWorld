"""
test_edge_test_command.py — Que el informe se pueda leer, y que diga lo que hay.

La parte que se rompe sin que nadie lo note no es el cálculo: es la impresión. Un
`KeyError` en el renderizado tira el comando entero después de haber hecho todo
el trabajo, y una clave que se imprime mal convierte un resultado correcto en una
conclusión equivocada.

Los tests sustituyen el cálculo por informes fijos. Lo que se comprueba aquí es
la traducción de un diccionario a algo que un humano pueda leer sin equivocarse.
"""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


def _report(**overrides):
    base = {
        "symbol": "BTC", "interval": "1h", "candles": 8000, "data_source": "binance",
        "horizon_bars": 24, "rv_window_bars": 24, "n_splits": 5,
        "verdict": "VOLATILITY",
        "conclusion": "La volatilidad es predecible; la dirección no.",
        "direction": {
            "answerable": False, "n_oos": 3200, "accuracy": 0.51, "baseline": 0.52,
            "edge": -0.01, "edge_ci": [-0.03, 0.01], "significant": False,
            "observations_needed": None, "note": "El edge observado no es positivo.",
        },
        "volatility": {
            "answerable": True, "n_oos": 3200, "predictable": True,
            "best_predictor": "persistence", "alpha_per_candidate": 0.025,
            "correlation": 0.61, "correlation_significant": True,
            "oos_r2_vs_constant": 0.34, "beats_constant": True,
            "har_beats_persistence": False, "oos_r2_har_vs_persistence": 0.02,
            "candidates": {
                "persistence": {"oos_r2_vs_constant": 0.34, "beats_constant": True,
                                "correlation": 0.61, "correlation_significant": True,
                                "works": True, "dm_vs_constant": {}},
                "har": {"oos_r2_vs_constant": 0.31, "beats_constant": True,
                        "correlation": 0.58, "correlation_significant": True,
                        "works": True, "dm_vs_constant": {}},
            },
            "observations_needed": 18, "note": "El mejor predictor es «persistence».",
        },
        "power_reference": {
            "direction_edge_1pct": 15456, "direction_edge_2pct": 3863,
            "direction_edge_5pct": 618, "volatility_r030": 68, "volatility_r045": 30,
            "note": "Observaciones necesarias con 80 % de potencia.",
        },
        "protocol": "Validación purgada; la nula es la MEDIA CONSTANTE.",
    }
    base.update(overrides)
    return base


@pytest.fixture
def stub(monkeypatch):
    """Sustituye el cálculo, deja el renderizado."""
    def _install(report):
        import core.management.commands.edge_test as cmd
        monkeypatch.setattr(cmd.EdgeTestUseCase, "execute",
                            lambda self, *a, **k: report)
    return _install


def _run(*args, **kwargs):
    out = StringIO()
    call_command("edge_test", *args, stdout=out, stderr=out, **kwargs)
    return out.getvalue()


class TestTheReportReads:

    @pytest.mark.unit
    def test_it_prints_the_verdict(self, stub):
        stub(_report())
        assert "VOLATILITY" in _run("BTC")

    @pytest.mark.unit
    def test_it_prints_every_candidate_not_just_the_winner(self, stub):
        """Ver solo el ganador impide notar que los dos empatan, que es
        justamente cuando el «mejor predictor» no significa gran cosa."""
        stub(_report())
        salida = _run("BTC")
        assert "persistence" in salida and "har" in salida

    @pytest.mark.unit
    def test_the_power_table_travels_with_the_verdict(self, stub):
        """Sin ella, un NEITHER direccional se lee como «no hay edge» cuando dice
        «con esta muestra no se puede saber»."""
        stub(_report())
        salida = _run("BTC")
        assert "15,456" in salida and "3,863" in salida

    @pytest.mark.unit
    def test_the_protocol_is_printed(self, stub):
        stub(_report())
        assert "MEDIA CONSTANTE" in _run("BTC")

    @pytest.mark.unit
    def test_har_versus_persistence_is_labelled_as_model_selection(self, stub):
        """Es la confusión que costó dos criterios equivocados. Que la etiqueta
        viaje con el número es lo que impide repetirla al leer el informe."""
        stub(_report())
        assert "no evidencia" in _run("BTC")

    @pytest.mark.unit
    def test_a_neither_verdict_also_renders(self, stub):
        """El camino con `predictable` en falso pasa por ramas distintas; si
        reventara, reventaría justo en el resultado que más importa comunicar."""
        r = _report(verdict="NEITHER", conclusion="Ninguna de las dos muestra señal.")
        r["volatility"].update(predictable=False, best_predictor=None,
                               correlation=None, oos_r2_vs_constant=None)
        stub(r)
        assert "NEITHER" in _run("BTC")

    @pytest.mark.unit
    def test_an_error_report_is_shown_instead_of_crashing(self, stub):
        stub({"symbol": "BTC", "error": "Se necesitan al menos 300 velas y hay 12.",
              "candles_available": 12})
        assert "300 velas" in _run("BTC")

    @pytest.mark.unit
    def test_a_short_report_without_optional_keys_still_renders(self, stub):
        """Cuando la muestra no llega, `_volatility_question` devuelve un
        diccionario mínimo. El renderizado no puede asumir las claves del caso
        completo."""
        r = _report(verdict="NEITHER")
        r["direction"] = {"answerable": False, "n_oos": 0, "note": "Muestra corta."}
        r["volatility"] = {"answerable": False, "n_oos": 0, "predictable": False,
                           "note": "Muestra corta."}
        stub(r)
        assert "Muestra corta." in _run("BTC")


class TestItsArguments:

    @pytest.mark.unit
    def test_several_symbols_in_one_run(self, stub):
        stub(_report())
        assert _run("BTC", "ETH").count("VEREDICTO") == 2

    @pytest.mark.unit
    def test_json_output_is_parseable(self, stub):
        import json
        stub(_report())
        datos = json.loads(_run("BTC", "--json"))
        assert datos[0]["verdict"] == "VOLATILITY"

    @pytest.mark.unit
    def test_json_output_carries_the_full_report_not_the_summary(self, stub):
        """El volcado existe para poder auditar el resultado meses después; si
        perdiera los candidatos, no se podría reconstruir por qué dijo lo que
        dijo."""
        import json
        stub(_report())
        datos = json.loads(_run("BTC", "--json"))
        assert "candidates" in datos[0]["volatility"]
        assert "protocol" in datos[0]

    @pytest.mark.unit
    def test_a_non_positive_horizon_is_refused(self):
        """El horizonte es también lo que se purga: un cero desactivaría la purga
        en silencio, que es la fuga que todo este trabajo cierra."""
        with pytest.raises(CommandError):
            _run("BTC", "--horizon", "0")

    @pytest.mark.unit
    def test_a_non_positive_window_is_refused(self):
        with pytest.raises(CommandError):
            _run("BTC", "--rv-window", "0")
