"""
test_experiment_registry.py — Registro de experimentos y estado honesto (G8+G9).

Dos garantías de gobernanza:

  · **Append-only.** Un registro de experimentos que se puede reescribir no
    sirve para nada: el sentido de anotar cada búsqueda es que el número de
    pruebas realizadas no pueda maquillarse a posteriori.
  · **«Validada» significa algo.** Antes se marcaba `validated` a todo el
    ranking sin mirar el holdout, de modo que la etiqueta afirmaba más de lo
    que el dato sostenía.
"""

import pytest

from core.application.use_cases.generate_strategies import _status_for


class TestAppendOnly:

    @pytest.mark.integration
    def test_a_registered_run_cannot_be_modified(self, db):
        from core.infrastructure.persistence.models import StrategyExperimentRun

        run = StrategyExperimentRun.objects.create(
            asset_symbol="BTC", interval="1d", evaluations=1200, passed_gating=2,
        )

        run.evaluations = 5
        with pytest.raises(ValueError, match="append-only"):
            run.save()

        run.refresh_from_db()
        assert run.evaluations == 1200

    @pytest.mark.integration
    def test_cumulative_trials_add_up_per_asset(self, db):
        """El dato de gobernanza: cuántas configuraciones se han probado sobre
        este activo sumando todas las búsquedas, incluidas las que no dieron
        nada."""
        from django.db.models import Sum
        from core.infrastructure.persistence.models import StrategyExperimentRun

        for n in (500, 1200, 300):
            StrategyExperimentRun.objects.create(
                asset_symbol="ETH", interval="1d", evaluations=n,
            )
        StrategyExperimentRun.objects.create(
            asset_symbol="BTC", interval="1d", evaluations=999,
        )

        total = (StrategyExperimentRun.objects.filter(asset_symbol="ETH", interval="1d")
                 .aggregate(t=Sum("evaluations"))["t"])
        assert total == 2000

    @pytest.mark.integration
    def test_survives_the_asset_being_deleted(self, db):
        """El histórico debe seguir diciendo sobre qué se buscó aunque el activo
        desaparezca del catálogo."""
        from core.infrastructure.persistence.models import CryptoAsset, StrategyExperimentRun

        asset = CryptoAsset.objects.create(symbol="DOGE", name="Dogecoin", current_price=1)
        run = StrategyExperimentRun.objects.create(
            asset=asset, asset_symbol="DOGE", interval="1d", evaluations=42,
        )
        asset.delete()

        run.refresh_from_db()
        assert run.asset_id is None
        assert run.asset_symbol == "DOGE"
        assert run.evaluations == 42


class TestCatalogVersion:

    @pytest.mark.unit
    def test_is_stable_across_calls(self):
        from core.domain.services.strategy_spec import catalog_version
        assert catalog_version() == catalog_version()

    @pytest.mark.unit
    def test_changes_when_the_search_space_changes(self, monkeypatch):
        """Añadir un bloque o mover el rango de un parámetro cambia el espacio:
        dos ejecuciones con la misma semilla dejan de ser comparables y la
        huella tiene que delatarlo."""
        from core.domain.services import strategy_spec as spec

        before = spec.catalog_version()
        monkeypatch.setitem(spec._ALL, "FAKE_BLOCK",
                            {"params": {"window": ("int", 5, 10)}})
        assert spec.catalog_version() != before


class TestValidatedRequiresHoldout:

    @pytest.mark.unit
    def test_positive_holdout_is_validated(self):
        assert _status_for({
            "passed_gating": True,
            "holdout_validation": {"sharpe": 1.4, "n_trades": 12},
        }) == "validated"

    @pytest.mark.unit
    def test_losing_holdout_is_only_a_candidate(self):
        """Pasar el gating es superar controles sobre la MISMA zona en la que se
        buscó. Perder en datos jamás vistos no es validación."""
        assert _status_for({
            "passed_gating": True,
            "holdout_validation": {"sharpe": -0.6, "n_trades": 9},
        }) == "candidate"

    @pytest.mark.unit
    def test_no_trades_in_holdout_is_not_evidence(self):
        """Sin operaciones no hay evidencia ni a favor ni en contra."""
        assert _status_for({
            "passed_gating": True,
            "holdout_validation": {"sharpe": 0.0, "n_trades": 0},
        }) == "candidate"

    @pytest.mark.unit
    def test_failing_the_gating_is_never_validated(self):
        assert _status_for({
            "passed_gating": False,
            "holdout_validation": {"sharpe": 3.0, "n_trades": 30},
        }) == "candidate"

    @pytest.mark.unit
    def test_missing_holdout_block_is_not_validated(self):
        assert _status_for({"passed_gating": True}) == "candidate"
