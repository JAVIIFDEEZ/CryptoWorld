"""
export_reports.py — Exportación de informes en CSV (uso profesional).

Genera CSV descargables — el formato universal de intercambio para análisis
posterior (Excel, Python, R) — de:
  · positions: posiciones manuales abiertas y cerradas con su P&L.
  · risk:      exposición firmada agregada por activo + resumen de VaR/CVaR.

Solo stdlib (`csv`, `io`), sin dependencias. Cada fila es del usuario dueño.
"""

import csv
import io


def _writer():
    buf = io.StringIO()
    return buf, csv.writer(buf)


def export_positions_csv(owner) -> str:
    from core.infrastructure.persistence.models import Position

    buf, w = _writer()
    w.writerow(["symbol", "direction", "status", "avg_entry_price", "open_quantity",
                "initial_quantity", "realized_pnl", "current_price", "market_value_usd",
                "unrealized_pnl_usd", "opened_at", "closed_at"])
    for p in (Position.objects.select_related("asset")
              .filter(user=owner).order_by("-opened_at")):
        price = float(p.asset.current_price or 0)
        qty = float(p.open_quantity or 0)
        entry = float(p.avg_entry_price or 0)
        mkt = qty * price
        sign = 1.0 if p.direction == "LONG" else -1.0
        unreal = sign * qty * (price - entry) if p.status == "OPEN" else 0.0
        w.writerow([
            p.asset.symbol, p.direction, p.status, entry, qty,
            float(p.initial_quantity or 0), float(p.realized_pnl or 0), price,
            round(mkt, 2), round(unreal, 2),
            p.opened_at.isoformat() if p.opened_at else "",
            p.closed_at.isoformat() if p.closed_at else "",
        ])
    return buf.getvalue()


def export_risk_csv(owner) -> str:
    from core.application.use_cases.portfolio_risk import PortfolioRiskUseCase

    risk = PortfolioRiskUseCase().execute(owner)
    buf, w = _writer()
    # Bloque 1: exposición por activo
    w.writerow(["# EXPOSICIÓN POR ACTIVO"])
    w.writerow(["symbol", "net_usd", "manual_usd", "paper_usd", "live_usd", "in_var"])
    for e in risk.get("exposures", []):
        bb = e.get("by_book", {})
        w.writerow([e["symbol"], e["net_usd"], bb.get("manual", 0),
                    bb.get("paper", 0), bb.get("live", 0), e.get("in_var")])
    # Bloque 2: resumen agregado + VaR
    w.writerow([])
    w.writerow(["# RESUMEN DE RIESGO"])
    v = risk.get("var") or {}
    rows = [
        ("gross_usd", risk.get("gross_usd")),
        ("net_usd", risk.get("net_usd")),
        ("long_usd", risk.get("long_usd")),
        ("short_usd", risk.get("short_usd")),
        ("top_concentration_pct", risk.get("top_concentration_pct")),
        ("var_status", v.get("status")),
        ("var95_usd", v.get("var95_usd")),
        ("cvar95_usd", v.get("cvar95_usd")),
        ("var99_usd", v.get("var99_usd")),
        ("cvar99_usd", v.get("cvar99_usd")),
        ("worst_day_usd", v.get("worst_day_usd")),
        ("var_days", v.get("days")),
    ]
    w.writerow(["metric", "value"])
    for k, val in rows:
        w.writerow([k, val if val is not None else ""])
    return buf.getvalue()


EXPORTERS = {
    "positions": ("posiciones", export_positions_csv),
    "risk": ("riesgo", export_risk_csv),
}
