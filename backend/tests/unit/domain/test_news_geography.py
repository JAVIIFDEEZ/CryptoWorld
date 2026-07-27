"""
tests/unit/domain/test_news_geography.py — Clasificación geo/temática de noticias.
"""

import pytest

from core.domain.services.news_geography import classify_news_geography


def _item(title, body="", sentiment="neutral"):
    return {"title": title, "body": body, "sentiment": sentiment,
            "url": "https://x", "published_at": "2026-07-06T10:00:00Z"}


class TestClassification:

    @pytest.mark.unit
    def test_regions_and_categories_detected(self):
        out = classify_news_geography([
            _item("La Reserva Federal anuncia una bajada de tipos de interés"),
            _item("Fed chair Powell hints at another rate cut in Washington"),
            _item("El BCE mantiene la política monetaria en la eurozona"),
            _item("Missile attack escalates war in Ukraine"),
            _item("Exchange gigante anuncia su salida a bolsa (IPO) en el Nasdaq"),
            _item("Un protocolo DeFi sufre un hack de $40M"),  # sin región
        ])
        by_region = {m["region"]: m for m in out["markers"]}
        # EEUU: dos monetarias + la IPO (Nasdaq)
        assert by_region["eeuu"]["count"] == 3
        assert by_region["eeuu"]["categories"]["monetary"] == 2
        assert by_region["eeuu"]["categories"]["ipo_listing"] == 1
        assert by_region["eurozona"]["top_category"] == "monetary"
        assert by_region["ucrania"]["top_category"] == "conflict"
        # La noticia del hack no tiene región: global, sin coordenadas inventadas
        assert out["unlocated"] == 1
        assert out["located"] == 5 and out["total"] == 6

    @pytest.mark.unit
    def test_conflict_weighs_more_than_adoption(self):
        out = classify_news_geography([
            _item("War escalates near Kyiv, Ukraine"),
            _item("Retailer in Brazil accepts bitcoin payments (adoption)"),
        ])
        assert out["markers"][0]["region"] == "ucrania"   # ordenado por importancia

    @pytest.mark.unit
    def test_marker_shape_ready_for_globe(self):
        out = classify_news_geography([_item("Bank of Japan interest rate decision in Tokyo")])
        m = out["markers"][0]
        assert m["region"] == "japon"
        assert -90 <= m["lat"] <= 90 and -180 <= m["lon"] <= 180
        assert m["items"][0]["category"] == "monetary"
        assert m["items"][0]["title"]
