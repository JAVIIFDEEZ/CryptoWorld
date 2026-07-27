"""
tests/integration/test_confluence_and_landing.py — Confluence Card + SEO.

Verifican el contrato completo de la feature:
  - Endpoint REST autenticado /api/assets/<symbol>/confluence/
  - Landing pública /cripto/<slug> renderizada por servidor: el HTML
    CRUDO (sin ejecutar JS) contiene el veredicto y el análisis — la
    prueba de que es indexable por buscadores.
  - sitemap.xml y robots.txt

El fetch de OHLCV se sustituye por datos sintéticos (sin red).
"""

import math

import pandas as pd
import pytest

from core.application.use_cases.ohlcv_fetcher import OhlcvFetchResult
from core.infrastructure.persistence.models import CryptoAsset


def _make_df(rows: int = 300) -> pd.DataFrame:
    closes = [
        100.0 + 0.3 * i + 8.0 * math.sin(2 * math.pi * i / 20)
        for i in range(rows)
    ]
    return pd.DataFrame({
        "timestamp": [1700000000000 + i * 86_400_000 for i in range(rows)],
        "open": [c * 0.995 for c in closes],
        "high": [c * 1.01 for c in closes],
        "low": [c * 0.99 for c in closes],
        "close": closes,
        "volume": [1000.0 + i for i in range(rows)],
    })


@pytest.fixture
def btc_asset(db):
    return CryptoAsset.objects.create(
        symbol="BTC",
        name="Bitcoin",
        current_price=100,
        coingecko_id="bitcoin",
        logo_url="https://example.com/btc.png",
    )


@pytest.fixture
def fake_ohlcv(monkeypatch):
    """Evita la red: el caso de uso recibe siempre el DataFrame sintético."""
    def _fake(symbol, interval="1d", limit=365, **kwargs):
        return OhlcvFetchResult(df=_make_df(), source="binance")

    monkeypatch.setattr(
        "core.application.use_cases.get_confluence_card.fetch_ohlcv_dataframe",
        _fake,
    )


class TestConfluenceRestEndpoint:

    @pytest.mark.integration
    def test_requires_authentication(self, api_client, btc_asset):
        response = api_client.get("/api/assets/BTC/confluence/")
        assert response.status_code == 401

    @pytest.mark.integration
    def test_returns_full_card(self, authenticated_client, btc_asset, fake_ohlcv):
        response = authenticated_client.get("/api/assets/BTC/confluence/")
        assert response.status_code == 200
        data = response.data
        assert data["symbol"] == "BTC"
        assert data["name"] == "Bitcoin"
        assert data["slug"] == "bitcoin"
        assert data["verdict"]["verdict"] in (
            "COMPRA_FUERTE", "COMPRA", "NEUTRAL", "VENTA", "VENTA_FUERTE"
        )
        assert len(data["analysis_paragraphs"]) == 5
        assert data["support_resistance"]["supports"] or data["support_resistance"]["resistances"]

    @pytest.mark.integration
    def test_unknown_symbol_returns_404(self, authenticated_client, db):
        response = authenticated_client.get("/api/assets/NOPE/confluence/")
        assert response.status_code == 404


class TestSeoLanding:

    @pytest.mark.integration
    def test_landing_html_is_indexable_without_js(self, client, btc_asset, fake_ohlcv):
        """Criterio de aceptación: el HTML crudo contiene la ficha completa."""
        response = client.get("/cripto/bitcoin")
        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/html")

        html = response.content.decode("utf-8")
        # Contenido visible sin ejecutar JavaScript
        assert "Análisis técnico de Bitcoin (BTC)" in html
        assert "Veredicto:" in html
        assert "cotiza actualmente en" in html          # narrativa del dominio
        assert "asesoramiento financiero" in html       # disclaimer
        assert "Soportes y resistencias" in html
        assert "Fibonacci" in html
        # Sin rastro de la SPA: no requiere bundle JS para mostrar contenido
        assert "/src/main.tsx" not in html

    @pytest.mark.integration
    def test_landing_has_unique_seo_metadata(self, client, btc_asset, fake_ohlcv):
        html = client.get("/cripto/bitcoin").content.decode("utf-8")
        assert "<title>Bitcoin (BTC)" in html
        assert '<meta name="description" content="Análisis técnico de Bitcoin (BTC)' in html
        assert '<link rel="canonical"' in html and "/cripto/bitcoin" in html
        assert '<meta property="og:title"' in html
        assert '<script type="application/ld+json">' in html
        assert '"@type": "Article"' in html

    @pytest.mark.integration
    def test_landing_accepts_symbol_as_alias(self, client, btc_asset, fake_ohlcv):
        response = client.get("/cripto/btc")
        assert response.status_code == 200

    @pytest.mark.integration
    def test_landing_interlinks_other_assets(self, client, btc_asset, fake_ohlcv):
        """Interlinking SEO: la landing enlaza a otras criptos del catálogo."""
        CryptoAsset.objects.create(
            symbol="ETH", name="Ethereum", current_price=3000,
            coingecko_id="ethereum", market_cap=400_000_000_000,
        )
        html = client.get("/cripto/bitcoin").content.decode("utf-8")
        assert "Otras criptomonedas analizadas" in html
        assert "/cripto/ethereum" in html
        assert "Ethereum (ETH)" in html

    @pytest.mark.integration
    def test_landing_unknown_slug_is_404(self, client, db):
        assert client.get("/cripto/no-existe").status_code == 404


class TestSitemapAndRobots:

    @pytest.mark.integration
    def test_sitemap_lists_asset_landings(self, client, btc_asset):
        response = client.get("/sitemap.xml")
        assert response.status_code == 200
        assert response["Content-Type"].startswith("application/xml")
        body = response.content.decode("utf-8")
        assert "<urlset" in body
        assert "/cripto/bitcoin</loc>" in body

    @pytest.mark.integration
    def test_robots_allows_crawl_and_announces_sitemap(self, client, db):
        response = client.get("/robots.txt")
        assert response.status_code == 200
        body = response.content.decode("utf-8")
        assert "User-agent: *" in body
        assert "Sitemap:" in body and "/sitemap.xml" in body
        assert "Disallow: /api/" in body
