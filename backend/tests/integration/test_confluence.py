"""
tests/integration/test_confluence.py — Motor de confluencia 360° (caso de uso).

Con las cuatro fuentes simuladas: fusión completa con desglose y pesos, registro
de la lectura para aprendizaje (una sola pendiente por activo), resolución al
vencer el horizonte contra el precio real y el bucle completo pesos-aprendidos.
"""

from datetime import timedelta

import pandas as pd
import pytest
from django.utils import timezone

from core.application.use_cases.get_confluence import (
    GetConfluenceUseCase, ResolveConfluenceSnapshotsUseCase,
)


def _mock_sources(monkeypatch, technical=0.6, ml=0.4, onchain=0.5, news=0.3):
    UC = "core.application.use_cases.get_confluence.GetConfluenceUseCase"
    monkeypatch.setattr(f"{UC}._technical", staticmethod(
        lambda symbol: {"available": True, "score": technical, "detail": "t", "last_price": 100.0}))
    monkeypatch.setattr(f"{UC}._ml", staticmethod(
        lambda symbol: {"available": True, "score": ml, "detail": "m"}))
    monkeypatch.setattr(f"{UC}._onchain", staticmethod(
        lambda: {"available": True, "score": onchain, "detail": "o"}))
    monkeypatch.setattr(f"{UC}._news", staticmethod(
        lambda symbol: {"available": True, "score": news, "detail": "n"}))


class TestGetConfluence:

    @pytest.mark.integration
    def test_full_reading_with_breakdown_and_snapshot(self, db, monkeypatch):
        from core.infrastructure.persistence.models import ConfluenceSnapshot

        _mock_sources(monkeypatch)
        out = GetConfluenceUseCase().execute("BTC")
        assert out["verdict"] == "CONFLUENCIA_ALCISTA"
        assert set(out["sources"]) == {"technical", "ml", "onchain", "news"}
        src = out["sources"]["technical"]
        assert src["weight"] > 0 and src["weight_mode"] == "a_priori"
        # La lectura direccional queda registrada para verificarse a las 24h
        snap = ConfluenceSnapshot.objects.get()
        assert snap.asset_symbol == "BTC" and snap.status == "pending"
        assert snap.price_at == 100.0 and set(snap.scores) == set(out["sources"])

        # Releer NO duplica la pendiente (las recargas no inflan el historial)
        GetConfluenceUseCase().execute("BTC")
        assert ConfluenceSnapshot.objects.count() == 1

    @pytest.mark.integration
    def test_degrades_to_insufficient_with_one_source(self, db, monkeypatch):
        UC = "core.application.use_cases.get_confluence.GetConfluenceUseCase"
        _mock_sources(monkeypatch)
        for m in ("_ml", "_news"):
            monkeypatch.setattr(f"{UC}.{m}", staticmethod(
                lambda *a: {"available": False, "score": None, "detail": "caída"}))
        monkeypatch.setattr(f"{UC}._onchain", staticmethod(
            lambda: {"available": False, "score": None, "detail": "caída"}))
        out = GetConfluenceUseCase().execute("BTC")
        assert out["verdict"] == "INSUFICIENTE"
        from core.infrastructure.persistence.models import ConfluenceSnapshot
        assert ConfluenceSnapshot.objects.count() == 0   # no se aprende de nada


class TestResolutionLoop:

    @pytest.mark.integration
    def test_resolution_feeds_weight_learning(self, db, monkeypatch):
        from core.infrastructure.persistence.models import ConfluenceSnapshot

        # Lectura vencida: precio 100 → 110 (+10%): las fuentes alcistas acertaron
        ConfluenceSnapshot.objects.create(
            asset_symbol="ETH", scores={"technical": 0.6, "ml": -0.4},
            fused_score=0.3, verdict="MIXTO", price_at=100.0,
            resolve_at=timezone.now() - timedelta(minutes=5),
        )

        class _Res:
            df = pd.DataFrame({"close": [109.0, 110.0]})
            source = "binance"
        monkeypatch.setattr(
            "core.application.use_cases.ohlcv_fetcher.fetch_ohlcv_dataframe",
            lambda symbol, interval="1h", limit=2, **kw: _Res(),
        )
        out = ResolveConfluenceSnapshotsUseCase().execute()
        assert out == {"due": 1, "resolved": 1}
        snap = ConfluenceSnapshot.objects.get()
        assert snap.status == "resolved"
        assert snap.actual_return_pct == pytest.approx(10.0)

        # El aprendizaje ve la fila: técnica acertó (+), ml falló (−)
        from core.domain.services.confluence_fusion import learn_weights
        rows = list(ConfluenceSnapshot.objects.filter(status="resolved")
                    .values("scores", "actual_return_pct"))
        stats = learn_weights(rows)
        assert stats["technical"]["n"] == 1 and stats["ml"]["n"] == 1


class TestApi:

    @pytest.mark.integration
    def test_requires_auth(self, api_client):
        assert api_client.get("/api/analysis/confluence/?symbol=BTC").status_code == 401

    @pytest.mark.integration
    def test_endpoint_returns_reading(self, authenticated_client, monkeypatch):
        from django.core.cache import cache
        cache.delete("confluence:BTC")
        _mock_sources(monkeypatch)
        resp = authenticated_client.get("/api/analysis/confluence/?symbol=BTC")
        assert resp.status_code == 200
        assert set(resp.data) >= {"asset_symbol", "score", "verdict", "sources",
                                  "agreement_pct", "horizon_hours"}


class TestScheduledEvaluation:

    @pytest.mark.integration
    def test_transitions_create_events_and_repeats_do_not(self, db, monkeypatch):
        from core.application.use_cases.get_confluence import EvaluateConfluenceUseCase
        from core.infrastructure.persistence.models import ConfluenceSignalEvent

        _mock_sources(monkeypatch)   # todas alcistas → CONFLUENCIA_ALCISTA
        uc = EvaluateConfluenceUseCase()

        out1 = uc.execute(symbols=["BTC"])
        assert out1["transitions"] == 1
        ev = ConfluenceSignalEvent.objects.get()
        assert ev.verdict == "CONFLUENCIA_ALCISTA" and ev.previous_verdict == ""

        # Mismo veredicto en la siguiente pasada: SIN evento nuevo
        out2 = uc.execute(symbols=["BTC"])
        assert out2["transitions"] == 0
        assert ConfluenceSignalEvent.objects.count() == 1

        # Cambio de régimen (fuentes bajistas) → nuevo evento con el anterior
        _mock_sources(monkeypatch, technical=-0.6, ml=-0.5, onchain=-0.4, news=-0.3)
        out3 = uc.execute(symbols=["BTC"])
        assert out3["transitions"] == 1
        last = ConfluenceSignalEvent.objects.order_by("-created_at").first()
        assert last.verdict == "CONFLUENCIA_BAJISTA"
        assert last.previous_verdict == "CONFLUENCIA_ALCISTA"

    @pytest.mark.integration
    def test_confluence_events_reach_notifications_feed(self, db, test_user, monkeypatch):
        from core.application.use_cases.get_confluence import EvaluateConfluenceUseCase
        from core.application.use_cases.notifications import NotificationsFeedUseCase

        _mock_sources(monkeypatch)
        EvaluateConfluenceUseCase().execute(symbols=["BTC"])
        feed = NotificationsFeedUseCase().execute(owner=test_user)
        item = next(it for it in feed["items"] if it["kind"] == "confluence")
        assert "BTC" in item["title"] and item["link"] == "/analysis"
        assert feed["unread"] >= 1


class TestHierarchyAndRecordInPayload:

    @pytest.mark.integration
    def test_payload_includes_track_record_and_weight_modes(self, db, monkeypatch):
        _mock_sources(monkeypatch)
        out = GetConfluenceUseCase().execute("BTC")
        assert "track_record" in out and "overall" in out["track_record"]
        modes = {s["weight_mode"] for s in out["sources"].values()}
        assert modes <= {"aprendido_activo", "aprendido_global", "a_priori"}
