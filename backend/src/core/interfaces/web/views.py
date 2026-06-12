"""
interfaces/web/views.py — Landings públicas SEO renderizadas por servidor.

A diferencia de la SPA (CSR en Vercel), estas vistas devuelven HTML
completo generado por Django: todo el contenido de la Confluence Card es
visible en el HTML crudo sin ejecutar JavaScript, que es lo que indexan
los buscadores. Vercel proxea /cripto/*, /sitemap.xml y /robots.txt hacia
este backend (ver vercel.json), de modo que las landings cuelgan del
mismo dominio público que la SPA.

Comparte el caso de uso (y su caché de 1 h) con el endpoint REST:
cero duplicación de lógica de dominio.
"""

import json

from django.conf import settings
from django.http import Http404, HttpResponse
from django.shortcuts import render
from django.views.decorators.cache import cache_page

from core.application.use_cases.get_confluence_card import (
    AssetNotFoundError,
    ConfluenceDataUnavailableError,
    GetConfluenceCardUseCase,
)
from core.infrastructure.persistence.models import CryptoAsset
from core.infrastructure.persistence.repositories_impl import (
    DjangoCryptoAssetRepository,
)

# Etiquetas de presentación (la lógica vive en el dominio; esto es UI)
_VERDICT_LABELS = {
    "COMPRA_FUERTE": ("Compra fuerte", "buy"),
    "COMPRA": ("Compra", "buy"),
    "NEUTRAL": ("Neutral", "neutral"),
    "VENTA": ("Venta", "sell"),
    "VENTA_FUERTE": ("Venta fuerte", "sell"),
}
_TREND_LABELS = {
    "ALCISTA": ("Alcista", "buy"),
    "LATERAL": ("Lateral", "neutral"),
    "BAJISTA": ("Bajista", "sell"),
}


def _public_base_url() -> str:
    """Dominio público canónico (el de la SPA; Vercel proxea /cripto/*)."""
    return settings.FRONTEND_URL.rstrip("/")


def _resolve_asset(slug: str) -> CryptoAsset:
    """Las landings usan el coingecko_id como slug ('bitcoin'); se acepta
    también el ticker ('btc') como alias para enlaces manuales."""
    asset = (
        CryptoAsset.objects.filter(coingecko_id__iexact=slug).first()
        or CryptoAsset.objects.filter(symbol__iexact=slug).first()
    )
    if asset is None:
        raise Http404("Activo no encontrado.")
    return asset


@cache_page(60 * 60)  # 1 h — alineado con la caché de la ficha
def crypto_landing(request, slug: str):
    """GET /cripto/<slug> — Ficha técnica pública e indexable de un activo."""
    asset = _resolve_asset(slug)

    use_case = GetConfluenceCardUseCase(asset_repo=DjangoCryptoAssetRepository())
    try:
        card = use_case.execute(asset.symbol).as_dict()
    except (AssetNotFoundError, ConfluenceDataUnavailableError):
        # Sin datos no hay contenido que indexar: 404 evita thin content
        raise Http404("Ficha no disponible para este activo.")

    base_url = _public_base_url()
    canonical_url = f"{base_url}/cripto/{card['slug']}"
    verdict_label, verdict_tone = _VERDICT_LABELS[card["verdict"]["verdict"]]
    trend_label, trend_tone = _TREND_LABELS[card["trend"]["trend"]]

    title = (
        f"{card['name']} ({card['symbol']}) hoy: análisis técnico, "
        f"soportes y resistencias | CryptoWorld"
    )
    meta_description = (
        f"Análisis técnico de {card['name']} ({card['symbol']}): precio "
        f"{card['last_price']} USD, veredicto {verdict_label.lower()} con "
        f"{card['verdict']['confidence_pct']}% de confianza, tendencia "
        f"{trend_label.lower()}, niveles de soporte, resistencia y Fibonacci."
    )

    json_ld = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "Article",
            "headline": f"Análisis técnico de {card['name']} ({card['symbol']})",
            "description": meta_description,
            "inLanguage": "es",
            "datePublished": card["generated_at"],
            "dateModified": card["generated_at"],
            "mainEntityOfPage": canonical_url,
            "author": {"@type": "Organization", "name": "CryptoWorld"},
            "publisher": {"@type": "Organization", "name": "CryptoWorld"},
            "about": {"@type": "Thing", "name": card["name"]},
        },
        ensure_ascii=False,
    )

    context = {
        "card": card,
        "title": title,
        "meta_description": meta_description,
        "canonical_url": canonical_url,
        "json_ld": json_ld,
        "verdict_label": verdict_label,
        "verdict_tone": verdict_tone,
        "trend_label": trend_label,
        "trend_tone": trend_tone,
        "app_url": f"{base_url}/assets/{card['symbol']}",
        "base_url": base_url,
    }
    return render(request, "landing/crypto_card.html", context)


@cache_page(60 * 60)
def sitemap_xml(request):
    """GET /sitemap.xml — todas las landings de criptos del catálogo."""
    base_url = _public_base_url()
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for asset in CryptoAsset.objects.all().order_by("symbol"):
        slug = asset.coingecko_id or asset.symbol.lower()
        lastmod = asset.updated_at.date().isoformat() if asset.updated_at else ""
        lines.append(
            "<url>"
            f"<loc>{base_url}/cripto/{slug}</loc>"
            + (f"<lastmod>{lastmod}</lastmod>" if lastmod else "")
            + "<changefreq>daily</changefreq>"
            "<priority>0.8</priority>"
            "</url>"
        )
    lines.append("</urlset>")
    return HttpResponse("\n".join(lines), content_type="application/xml")


@cache_page(60 * 60 * 24)
def robots_txt(request):
    """GET /robots.txt — permite el rastreo y anuncia el sitemap."""
    base_url = _public_base_url()
    content = "\n".join(
        [
            "User-agent: *",
            "Disallow: /api/",
            "Disallow: /admin/",
            "Allow: /",
            "",
            f"Sitemap: {base_url}/sitemap.xml",
            "",
        ]
    )
    return HttpResponse(content, content_type="text/plain")
