"""
universe.py — Quién existía en cada momento, y qué cuesta olvidarlo.

Cualquier estudio que se haga «sobre el universo de cripto» se construye, por
defecto, con la lista de activos de HOY. Esa lista contiene únicamente a los que
sobrevivieron. Medir sobre ella no introduce un error pequeño ni acotado:

  · La mortalidad de activos en cripto es alta, y la supervivencia está
    correlacionada con el rendimiento — precisamente la variable que se mide.
  · Las muertes se concentran en los tramos bajistas, que son justo donde una
    estrategia tiene que demostrar que aguanta.
  · El efecto crece hacia atrás en el tiempo: cuanto más largo el histórico, más
    cadáveres faltan, y más optimista sale el backtest.

El resultado es un sesgo que **siempre va en la misma dirección**: hacia arriba.
Un motor que aspira a grado institucional no puede tener esa dirección fija en
un error suyo.

La corrección no es estadística, es de datos: hace falta saber cuándo empezó y
cuándo dejó de cotizar cada activo. Este módulo asume que esa información existe
(`listed_at` / `delisted_at`) y construye sobre ella el universo point-in-time,
además de **cuantificar** el sesgo para que nunca se pueda alegar ignorancia.

Capa de dominio: Python puro. Recibe registros ya materializados, no consulta BD.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class AssetLifecycle:
    """Ciclo de vida de un activo, independiente del ORM."""
    symbol: str
    listed_at: datetime | None = None
    delisted_at: datetime | None = None
    delisting_reason: str | None = None

    def tradable_at(self, moment: datetime) -> bool:
        """
        ¿Era operable en `moment`?

        `listed_at` desconocido se trata como «ya cotizaba»: inventar una fecha
        de alta excluiría datos reales, y ese error sí sería silencioso. La
        incertidumbre se reporta aparte, en `coverage`, en lugar de resolverse a
        escondidas dentro del filtro.
        """
        if self.listed_at is not None and moment < self.listed_at:
            return False
        return self.delisted_at is None or moment < self.delisted_at


def from_records(records) -> list[AssetLifecycle]:
    """Adapta filas del ORM (o dicts) al tipo de dominio."""
    out: list[AssetLifecycle] = []
    for r in records:
        get = r.get if isinstance(r, dict) else (lambda k, _r=r: getattr(_r, k, None))
        out.append(AssetLifecycle(
            symbol=str(get("symbol")),
            listed_at=get("listed_at"),
            delisted_at=get("delisted_at"),
            delisting_reason=get("delisting_reason"),
        ))
    return out


def point_in_time_universe(assets, as_of: datetime) -> list[str]:
    """Símbolos que cotizaban en `as_of`, incluidos los que ya no existen."""
    return sorted(a.symbol for a in assets if a.tradable_at(as_of))


def coverage(assets) -> dict:
    """
    Qué parte del universo tiene su ciclo de vida realmente conocido.

    Sin esto, un universo point-in-time construido sobre fechas mayormente nulas
    parecería riguroso siendo idéntico a la lista de supervivientes. La cifra
    honesta es esta, y debe viajar con cualquier resultado que la use.
    """
    total = len(assets)
    if total == 0:
        return {"n_assets": 0, "note": "Universo vacío."}

    with_listing = sum(1 for a in assets if a.listed_at is not None)
    dead = sum(1 for a in assets if a.delisted_at is not None)
    pct = with_listing / total * 100.0
    return {
        "n_assets": total,
        "with_listing_date": with_listing,
        "listing_coverage_pct": round(pct, 1),
        "delisted": dead,
        "reliable": pct >= 90.0 and dead > 0,
        "note": (
            f"{with_listing} de {total} activos ({pct:.0f}%) tienen fecha de alta "
            f"conocida y {dead} constan como retirados. "
            + ("El universo point-in-time es reconstruible con fiabilidad."
               if pct >= 90.0 and dead > 0 else
               "Sin fechas de alta ni bajas registradas, el universo point-in-time "
               "coincide con la lista de supervivientes y NO corrige el sesgo.")
        ),
    }


def survivorship_report(assets, as_of: datetime, now: datetime | None = None) -> dict:
    """
    Cuánto se distorsiona el universo de `as_of` si se reconstruye con la lista
    de hoy — que es lo que hace, sin decirlo, cualquier backtest sin este dato.

    `missing_pct` es la fracción del universo real de aquella fecha que ha
    desaparecido desde entonces: son los activos que un estudio ingenuo NO
    incluye, y son sistemáticamente los peores. `phantom_pct` es el problema
    inverso y menos comentado: activos que hoy existen pero entonces no
    cotizaban, y que un universo estático mete en una época a la que no
    pertenecen.
    """
    reference = now or datetime.now(tz=as_of.tzinfo)

    then = [a for a in assets if a.tradable_at(as_of)]
    if not then:
        return {"as_of": as_of.isoformat(), "n_then": 0,
                "note": "Ningún activo consta como cotizando en esa fecha."}

    survivors = [a for a in then if a.tradable_at(reference)]
    disappeared = [a for a in then if not a.tradable_at(reference)]
    phantom = [a for a in assets if a.tradable_at(reference) and not a.tradable_at(as_of)]

    missing_pct = len(disappeared) / len(then) * 100.0
    reasons: dict[str, int] = {}
    for a in disappeared:
        reasons[a.delisting_reason or "unknown"] = reasons.get(a.delisting_reason or "unknown", 0) + 1

    return {
        "as_of": as_of.isoformat(),
        "n_then": len(then),
        "n_survivors": len(survivors),
        "n_disappeared": len(disappeared),
        "missing_pct": round(missing_pct, 1),
        "phantom_pct": round(len(phantom) / len(then) * 100.0, 1),
        "reasons": reasons,
        "note": (
            f"De los {len(then)} activos que cotizaban en {as_of.date()}, "
            f"{len(disappeared)} ya no existen ({missing_pct:.0f}%). Un backtest "
            "construido con la lista de hoy los omite por completo, y son "
            "sistemáticamente los peores: el sesgo resultante siempre favorece a "
            "la estrategia."
        ),
    }
