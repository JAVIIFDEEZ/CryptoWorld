"""
test_showcase_trail.py — Nada de lo que se enseñó puede desaparecer sin cuenta.

El generador tiene dos pantallas y entre ellas había un silencio. Mientras
evoluciona enseña curvas de equity con retornos llamativos; al terminar, el
informe solo habla de las que llegaron al gating. Una candidata que se vio hacer
un +33 % podía no volver a aparecer, y desde fuera es imposible distinguir «la
descartaron por sobreajuste» de «se perdió por el camino». Lo primero es el
motor funcionando; lo segundo sería un fallo — y presentar los dos como silencio
es lo que hace desconfiar de la herramienta.

Aquí se fija que cada estrategia mostrada acabe en uno de cuatro destinos, y que
ninguno sea silencio.
"""

import pytest

from core.application.use_cases.generate_strategies import (
    SHOWCASE_ROWS, _showcase_trail,
)
from core.domain.services.strategy_evaluation import GatingThresholds


def _card(h: str, fitness: float = 1.0, ret: float = 30.0) -> dict:
    return {"hash": h, "description": f"spec {h}", "direction": "long",
            "fitness": fitness, "total_return_pct": ret,
            "max_drawdown_pct": 10.0, "n_trades": 20}


def _finalist(h: str, checks: dict | None = None, metrics: dict | None = None) -> dict:
    all_ok = {"min_trades": True, "no_lookahead": True, "wf_efficiency": True,
              "pbo": True, "mc_p5_positive": True, "sides_stand_alone": True}
    return {"spec_hash": h,
            "gating": {"checks": {**all_ok, **(checks or {})}, "metrics": metrics or {}}}


class TestDispositions:

    @pytest.mark.unit
    def test_a_strategy_in_the_book_says_so(self):
        out = _showcase_trail({"a": _card("a")}, [{"spec_hash": "a"}], [], {"a"},
                              GatingThresholds())
        assert out["rows"][0]["disposition"] == "in_book"

    @pytest.mark.unit
    def test_a_correlated_one_is_a_variant_not_a_discard(self):
        """Superó exactamente los mismos controles; lo que la aparta del libro es
        correlacionar con una cabeza, no fallar nada. Llamarla «descartada»
        sería mentir sobre su calidad."""
        passed = [{"spec_hash": "a", "variants": [{"spec_hash": "b"}]}]
        out = _showcase_trail({"b": _card("b")}, passed, [], {"a", "b"}, GatingThresholds())
        assert out["rows"][0]["disposition"] == "variant"

    @pytest.mark.unit
    def test_a_rejected_one_carries_what_it_failed(self):
        rejected = [_finalist("c", checks={"pbo": False}, metrics={"pbo": 0.62})]
        out = _showcase_trail({"c": _card("c")}, [], rejected, {"c"}, GatingThresholds())
        row = out["rows"][0]
        assert row["disposition"] == "rejected"
        assert row["detail"]["failed_checks"] == ["pbo"]
        assert row["detail"]["near_miss"]["gap"] == pytest.approx(0.12)

    @pytest.mark.unit
    def test_never_examined_is_not_a_verdict(self):
        """La distinción que evita leer un silencio como un rechazo: el gating
        tiene presupuesto limitado y se gasta por orden de fitness."""
        out = _showcase_trail({"d": _card("d")}, [], [], set(), GatingThresholds())
        assert out["rows"][0]["disposition"] == "not_gated"

    @pytest.mark.unit
    def test_approved_but_absent_from_the_book_is_a_variant(self):
        """Aprobó el gating y no está ni en el libro ni como variante declarada:
        la apartó el filtro de correlación. Marcarla `not_gated` diría que no se
        examinó, que es falso."""
        out = _showcase_trail({"e": _card("e")}, [], [], {"e"}, GatingThresholds())
        assert out["rows"][0]["disposition"] == "variant"

    @pytest.mark.unit
    def test_every_shown_strategy_gets_a_disposition(self):
        """La propiedad de fondo: ninguna se queda sin destino."""
        cards = {h: _card(h) for h in "abcdef"}
        out = _showcase_trail(cards, [{"spec_hash": "a"}],
                              [_finalist("b", checks={"pbo": False})], {"a", "b", "c"},
                              GatingThresholds())
        assert out["shown"] == 6
        assert all(r["disposition"] for r in out["rows"])
        assert sum(out["counts"].values()) == 6


class TestPresentation:

    @pytest.mark.unit
    def test_the_highest_fitness_comes_first(self):
        """Es el orden en el que el usuario las vio en el tablero, así que es
        donde va a buscar la que recuerda."""
        cards = {"lo": _card("lo", fitness=0.4), "hi": _card("hi", fitness=2.2)}
        out = _showcase_trail(cards, [], [], set(), GatingThresholds())
        assert [r["hash"] for r in out["rows"]] == ["hi", "lo"]

    @pytest.mark.unit
    def test_the_detail_is_capped_but_the_count_is_not(self):
        """El informe viaja por Redis y por la API: el detalle se recorta, pero
        el recuento sigue cubriéndolas todas — si no, el recorte parecería que
        se mostraron menos."""
        cards = {f"h{i}": _card(f"h{i}", fitness=float(i)) for i in range(40)}
        out = _showcase_trail(cards, [], [], set(), GatingThresholds())
        assert out["shown"] == 40
        assert len(out["rows"]) == SHOWCASE_ROWS
        assert sum(out["counts"].values()) == 40

    @pytest.mark.unit
    def test_the_note_says_the_return_is_in_sample(self):
        """Sin ese aviso la tabla se lee como un ranking de rentabilidad, y el
        usuario concluye que el motor tiró estrategias buenas."""
        out = _showcase_trail({"a": _card("a")}, [], [], set(), GatingThresholds())
        assert "dentro de muestra" in out["note"]

    @pytest.mark.unit
    def test_the_equity_curve_does_not_travel_in_the_report(self):
        """Son ~120 puntos por genoma. En el tablero en vivo se necesitan; en el
        informe final abultarían el payload sin aportar nada que no diga ya la
        ficha."""
        out = _showcase_trail({"a": _card("a")}, [], [], set(), GatingThresholds())
        assert "equity" not in out["rows"][0]

    @pytest.mark.unit
    def test_nothing_shown_gives_an_empty_trail_not_an_error(self):
        out = _showcase_trail({}, [], [], set(), GatingThresholds())
        assert out["shown"] == 0 and out["rows"] == []
