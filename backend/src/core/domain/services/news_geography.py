"""
news_geography.py — Clasificación geográfica y temática de noticias.

Convierte un feed de noticias en MARCADORES sobre el globo: detecta la región
del mundo a la que se refiere cada noticia (por entidades y palabras clave en
título/cuerpo, ES/EN) y su categoría de evento (política monetaria, regulación,
conflicto, salida a bolsa/listing, adopción, hackeo, macro). Las noticias sin
región identificable se cuentan aparte como «globales» — honestidad antes que
inventar coordenadas.

Capa de dominio: Python puro, sin red ni framework.
"""

from collections import defaultdict

# Región → (nombre, lat, lon, palabras clave). El orden importa: la primera
# región cuyo patrón case gana (las más específicas van antes que "EEUU").
REGIONS: list[tuple[str, str, float, float, tuple[str, ...]]] = [
    ("el_salvador", "El Salvador", 13.7, -89.2, ("el salvador", "bukele")),
    ("ucrania", "Ucrania", 50.4, 30.5, ("ukraine", "ucrania", "kyiv", "kiev")),
    ("rusia", "Rusia", 55.8, 37.6, ("russia", "rusia", "kremlin", "moscow", "moscú")),
    ("oriente_medio", "Oriente Medio", 31.8, 35.2, ("israel", "iran", "irán", "gaza", "middle east", "oriente medio", "hezbollah", "houthi")),
    ("golfo", "Golfo Pérsico", 25.2, 55.3, ("dubai", "uae", "emiratos", "abu dhabi", "saudi", "arabia saudí", "qatar")),
    ("reino_unido", "Reino Unido", 51.5, -0.1, ("bank of england", "boe", "uk ", "united kingdom", "reino unido", "london", "londres", "fca")),
    ("suiza", "Suiza", 46.9, 7.4, ("switzerland", "suiza", "snb", "zurich", "zúrich", "finma")),
    ("eurozona", "Eurozona", 50.1, 8.7, ("ecb", "bce", "eurozone", "eurozona", "european union", "unión europea", " eu ", "mica", "brussels", "bruselas", "frankfurt", "germany", "alemania", "france", "francia", "spain", "españa", "italy", "italia")),
    ("china", "China", 39.9, 116.4, ("china", "beijing", "pekín", "pboc", "yuan", "shanghai")),
    ("hong_kong", "Hong Kong", 22.3, 114.2, ("hong kong", "hkma")),
    ("japon", "Japón", 35.7, 139.7, ("japan", "japón", "boj", "bank of japan", "tokyo", "tokio", "yen")),
    ("corea", "Corea del Sur", 37.6, 127.0, ("korea", "corea", "seoul", "seúl", "won ")),
    ("india", "India", 28.6, 77.2, ("india", "rbi", "mumbai", "rupee", "rupia")),
    ("singapur", "Singapur", 1.35, 103.8, ("singapore", "singapur", "mas ")),
    ("australia", "Australia", -33.9, 151.2, ("australia", "rba", "sydney", "sídney")),
    ("brasil", "Brasil", -15.8, -47.9, ("brazil", "brasil", "real brasile")),
    ("argentina", "Argentina", -34.6, -58.4, ("argentina", "milei", "peso argentino")),
    ("mexico", "México", 19.4, -99.1, ("mexico", "méxico", "banxico")),
    ("canada", "Canadá", 45.4, -75.7, ("canada", "canadá", "ottawa", "toronto")),
    ("nigeria", "Nigeria", 9.1, 7.5, ("nigeria", "naira", "lagos")),
    ("turquia", "Turquía", 39.9, 32.9, ("turkey", "turquía", "lira turca", "istanbul", "estambul")),
    # EEUU al final: sus términos (fed, sec…) son los más frecuentes y genéricos.
    ("eeuu", "Estados Unidos", 38.9, -77.0, ("fed ", "federal reserve", "reserva federal", "sec ", "cftc", "white house", "casa blanca", "congress", "congreso de ee", "treasury", "tesoro de ee", " us ", "u.s.", "usa", "eeuu", "ee.uu", "estados unidos", "wall street", "new york", "nueva york", "washington", "powell", "trump", "nasdaq", "nyse")),
]

# Categoría → (nombre ES, palabras clave). La primera que case gana.
CATEGORIES: list[tuple[str, str, tuple[str, ...]]] = [
    ("conflict", "Conflicto/Geopolítica", ("war", "guerra", "attack", "ataque", "missile", "misil", "sanction", "sanción", "sanciones", "invasion", "invasión", "military", "militar", "conflict", "conflicto")),
    ("monetary", "Política monetaria", ("interest rate", "tipos de interés", "rate cut", "bajada de tipos", "rate hike", "subida de tipos", "inflation", "inflación", "cpi", "ipc", "quantitative", "monetary policy", "política monetaria", "central bank", "banco central")),
    ("ipo_listing", "Salida a bolsa/Listing", ("ipo", "salida a bolsa", "public offering", "listing", "goes public", "direct listing", "spac", "debut")),
    ("regulation", "Regulación", ("regulation", "regulación", "regulator", "regulador", "lawsuit", "demanda", "ley ", "bill ", "legislation", "legislación", "approval", "aprobación", "etf", "license", "licencia", "ban ", "prohibición", "compliance")),
    ("hack", "Hackeo/Seguridad", ("hack", "hackeo", "exploit", "breach", "stolen", "robo", "robados", "phishing", "drained", "vulnerability", "vulnerabilidad")),
    ("adoption", "Adopción", ("adoption", "adopción", "legal tender", "moneda de curso", "reserve", "reserva estratégica", "treasury buys", "integrates", "integra", "accepts", "acepta", "partnership", "acuerdo")),
    ("macro", "Macro", ("gdp", "pib", "recession", "recesión", "unemployment", "desempleo", "employment", "empleo", "jobs report", "deficit", "déficit", "debt ceiling", "techo de deuda")),
]

_IMPORTANCE_BY_CATEGORY = {
    "conflict": 3, "monetary": 3, "regulation": 2, "ipo_listing": 2,
    "hack": 2, "adoption": 1, "macro": 2,
}


def _match_region(text: str) -> tuple[str, str, float, float] | None:
    for key, name, lat, lon, kws in REGIONS:
        if any(kw in text for kw in kws):
            return key, name, lat, lon
    return None


def _match_category(text: str) -> tuple[str, str]:
    for key, name, kws in CATEGORIES:
        if any(kw in text for kw in kws):
            return key, name
    return "other", "Otros"


def classify_news_geography(items: list[dict], max_per_region: int = 6) -> dict:
    """
    Agrupa noticias por región del mundo con su categoría de evento dominante.

    `items`: dicts con al menos title; opcionales body, url, sentiment,
    published_at. Devuelve marcadores listos para el globo (lat/lon, tamaño por
    nº de noticias e importancia, desglose por categoría y titulares top) y el
    recuento honesto de noticias sin región identificable.
    """
    markers: dict[str, dict] = {}
    unlocated = 0

    for it in items:
        text = f"{it.get('title', '')} {it.get('body', '')}"[:500].lower()
        region = _match_region(text)
        cat_key, cat_name = _match_category(text)
        if region is None:
            unlocated += 1
            continue
        key, name, lat, lon = region
        m = markers.setdefault(key, {
            "region": key, "name": name, "lat": lat, "lon": lon,
            "count": 0, "importance": 0, "categories": defaultdict(int), "items": [],
        })
        m["count"] += 1
        m["importance"] += _IMPORTANCE_BY_CATEGORY.get(cat_key, 1)
        m["categories"][cat_key] += 1
        if len(m["items"]) < max_per_region:
            m["items"].append({
                "title": it.get("title", "")[:160],
                "url": it.get("url", ""),
                "category": cat_key,
                "category_name": cat_name,
                "sentiment": it.get("sentiment", "neutral"),
                "published_at": it.get("published_at"),
            })

    out = []
    for m in sorted(markers.values(), key=lambda x: x["importance"], reverse=True):
        cats = dict(m["categories"])
        top_cat = max(cats, key=cats.get) if cats else "other"
        out.append({**m, "categories": cats, "top_category": top_cat})

    return {
        "markers": out,
        "located": sum(m["count"] for m in out),
        "unlocated": unlocated,
        "total": len(items),
        "note": (
            "Regiones y categorías detectadas por entidades y palabras clave "
            "(ES/EN) en título y cuerpo. Las noticias sin región identificable "
            "se cuentan como globales, no se inventan coordenadas."
        ),
    }
