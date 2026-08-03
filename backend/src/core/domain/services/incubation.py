"""
incubation.py — Puerta de incubación antes del capital real.

Un backtest, por bien validado que esté, mide el pasado. La única evidencia que
no puede estar sobreajustada es la que llega **después** de haber fijado la
estrategia: rendimiento hacia delante, sobre datos que no existían cuando se
tomó la decisión.

Por eso una cartera de paper no puede promocionarse a ejecución real sin haber
incubado: un periodo mínimo funcionando en simulado, con un número mínimo de
operaciones y sin haberse degradado. Es el último filtro y el único que el
sobreajuste no puede burlar, porque no hay nada que ajustar sobre datos que
todavía no han ocurrido.

Es también la frontera de cumplimiento: poner capital real detrás de una
estrategia sin evidencia prospectiva es exactamente lo que un supervisor
señalaría.

Capa de dominio: sin Django, sin ORM. Recibe hechos y devuelve un veredicto.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class IncubationPolicy:
    """Requisitos para que una cartera pueda operar con dinero real."""
    min_days: int = 14          # dos semanas de funcionamiento hacia delante
    min_trades: int = 5         # evidencia mínima: una racha no es un historial
    require_profitable: bool = False
    # Rechazar carteras marcadas como decaídas (la estrategia se degradó en vivo).
    reject_decayed: bool = True


@dataclass(frozen=True)
class IncubationFacts:
    """Estado observado de la cartera, ya extraído de la persistencia."""
    days_running: float
    trades_count: int
    realized_pnl: float
    decayed: bool


def evaluate(facts: IncubationFacts, policy: IncubationPolicy | None = None) -> dict:
    """
    ¿Puede esta cartera pasar a ejecución real?

    Devuelve el veredicto con el detalle de cada requisito y cuánto falta para
    cumplirlo. El detalle importa: un «no» sin explicación empuja al usuario a
    buscar la forma de saltárselo, mientras que «te faltan 6 días y 2
    operaciones» convierte la barrera en un plazo.
    """
    pol = policy or IncubationPolicy()

    checks = {
        "min_days": facts.days_running >= pol.min_days,
        "min_trades": facts.trades_count >= pol.min_trades,
        "not_decayed": not (pol.reject_decayed and facts.decayed),
        "profitable": (not pol.require_profitable) or facts.realized_pnl > 0,
    }
    missing = [name for name, ok in checks.items() if not ok]

    return {
        "incubated": not missing,
        "checks": checks,
        "missing": missing,
        "days_running": round(float(facts.days_running), 1),
        "days_required": pol.min_days,
        "days_remaining": max(0, round(pol.min_days - facts.days_running, 1)),
        "trades_count": facts.trades_count,
        "trades_required": pol.min_trades,
        "trades_remaining": max(0, pol.min_trades - facts.trades_count),
        "note": _explain(checks, facts, pol),
    }


def _explain(checks: dict, facts: IncubationFacts, pol: IncubationPolicy) -> str:
    if all(checks.values()):
        return (f"Incubación superada: {facts.days_running:.0f} días en simulado y "
                f"{facts.trades_count} operaciones. La cartera puede operar en real.")

    reasons: list[str] = []
    if not checks["min_days"]:
        reasons.append(f"faltan {pol.min_days - facts.days_running:.0f} días de simulado")
    if not checks["min_trades"]:
        reasons.append(f"faltan {pol.min_trades - facts.trades_count} operaciones")
    if not checks["not_decayed"]:
        reasons.append("la estrategia se ha degradado en vivo")
    if not checks["profitable"]:
        reasons.append("el P&L acumulado en simulado no es positivo")

    return (
        "Incubación no superada: " + ", ".join(reasons) + ". La única evidencia "
        "que el sobreajuste no puede falsear es la que llega después de fijar la "
        "estrategia, y todavía no hay suficiente."
    )
