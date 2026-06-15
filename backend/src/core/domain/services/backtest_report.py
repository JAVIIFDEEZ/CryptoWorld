"""
backtest_report.py — Veredicto de robustez (Robustness Score + narrativa).

Combina los diagnósticos de la suite en una única puntuación 0-100 y un
veredicto en español (ROBUSTA / FRÁGIL / SOBREAJUSTADA) con 2-3 frases que
explican qué test falló. Determinista, sin LLM.

Capa de dominio: funciones puras sobre los dicts de diagnóstico.
"""

import numpy as np

VERDICT_ROBUST = "ROBUSTA"
VERDICT_FRAGILE = "FRÁGIL"
VERDICT_OVERFIT = "SOBREAJUSTADA"

# Pesos de cada componente sobre el score (se renormalizan si falta alguno).
# PBO y permutación pesan más: son los tests específicos de sobreajuste/edge;
# Monte Carlo y la eficiencia pueden inflarse por una racha afortunada.
_WEIGHTS = {
    "pbo": 0.30,
    "permutation": 0.20,
    "dsr": 0.20,
    "walk_forward": 0.20,
    "monte_carlo": 0.10,
}

# p-valor a partir del cual la permutación deja de aportar (no significativa)
_PERM_ALPHA = 0.10


def _clip01(x: float) -> float:
    return float(max(0.0, min(1.0, x)))


def build_robustness_report(diagnostics: dict) -> dict:
    """
    diagnostics debe contener: pbo, deflated_sharpe, walk_forward_rolling,
    walk_forward_anchored, monte_carlo, permutation, lookahead,
    recursive_instability. Devuelve score, veredicto y explicación.
    """
    pbo = diagnostics.get("pbo", {}).get("pbo")
    dsr = diagnostics.get("deflated_sharpe", {}).get("dsr")
    mc = diagnostics.get("monte_carlo", {})
    perm = diagnostics.get("permutation", {})
    wf_roll = diagnostics.get("walk_forward_rolling", {})
    wf_anch = diagnostics.get("walk_forward_anchored", {})
    lookahead = diagnostics.get("lookahead", {})
    recursive = diagnostics.get("recursive_instability", {})

    components: dict[str, float] = {}

    # PBO (menor es mejor)
    if pbo is not None:
        components["pbo"] = _clip01(1 - pbo)
    # Deflated Sharpe (ya es probabilidad 0..1)
    if dsr is not None:
        components["dsr"] = _clip01(dsr)
    # Walk-forward: media de eficiencia rolling y anchored (0 si OOS no es positivo)
    effs = []
    for wf in (wf_roll, wf_anch):
        eff = wf.get("efficiency")
        moos = wf.get("mean_oos_sharpe")
        if eff is not None and moos is not None:
            effs.append(_clip01(eff) if moos > 0 else 0.0)
    if effs:
        components["walk_forward"] = float(np.mean(effs))
    # Monte Carlo: probabilidad de beneficio
    prob_profit = mc.get("prob_profit_pct")
    if prob_profit is not None:
        components["monte_carlo"] = _clip01(prob_profit / 100.0)
    # Permutation: solo puntúa si el edge es (casi) significativo. Un p-valor
    # de 0.15 no es evidencia: con umbral, p≥0.10 → 0; p=0.05 → 0.5; p→0 → 1.
    p_value = perm.get("p_value")
    if p_value is not None:
        components["permutation"] = _clip01(1 - p_value / _PERM_ALPHA)

    total_w = sum(_WEIGHTS[k] for k in components)
    base = (
        sum(components[k] * _WEIGHTS[k] for k in components) / total_w
        if total_w > 0 else 0.0
    )
    score = base * 100

    # Guardarraíl: el PBO es el test de referencia de sobreajuste. Un PBO alto
    # impide considerar la estrategia robusta por muy bien que luzca el resto.
    if pbo is not None and pbo > 0.5:
        score = min(score, 64.0)   # no puede ser ROBUSTA (umbral 70)
    if pbo is not None and pbo > 0.7:
        score = min(score, 44.0)   # sobreajuste claro → SOBREAJUSTADA

    # Penalizaciones por sesgo
    if recursive.get("is_unstable"):
        score *= 0.90
    leak = bool(lookahead.get("is_leaky"))
    if leak:
        score = min(score, 15.0)  # un backtest con fuga del futuro no es fiable

    score = int(round(max(0.0, min(100.0, score))))

    # ── Razones (lo que falla) y fortalezas (lo que pasa) ──
    reasons: list[str] = []
    strengths: list[str] = []

    if leak:
        reasons.append(
            "se ha detectado fuga de información futura (lookahead): los "
            "resultados del backtest no son fiables"
        )
    if pbo is not None:
        if pbo > 0.5:
            reasons.append(f"la probabilidad de sobreajuste (PBO) es alta, {pbo:.0%}")
        elif pbo <= 0.3:
            strengths.append("baja probabilidad de sobreajuste (PBO)")
    if dsr is not None:
        if dsr < 0.5:
            reasons.append(
                f"el Deflated Sharpe es bajo ({dsr:.2f}): el Sharpe no sobrevive "
                f"al número de configuraciones probadas"
            )
        elif dsr >= 0.7:
            strengths.append("Deflated Sharpe sólido")
    if effs:
        mean_eff = float(np.mean(effs))
        if mean_eff < 0.5:
            reasons.append(
                "la eficiencia walk-forward es baja: el rendimiento fuera de "
                "muestra cae mucho respecto al de optimización"
            )
        elif mean_eff >= 0.7:
            strengths.append("buena consistencia walk-forward (OOS≈IS)")
    if p_value is not None:
        if p_value >= 0.05:
            reasons.append(
                f"el test de permutación no es significativo (p={p_value:.2f}): "
                f"el edge podría deberse al azar"
            )
        else:
            strengths.append("edge estadísticamente significativo (permutación)")
    if prob_profit is not None and prob_profit < 50:
        reasons.append(
            f"Monte Carlo estima solo un {prob_profit:.0f}% de probabilidad de beneficio"
        )
    if recursive.get("is_unstable"):
        reasons.append(
            "el indicador presenta inestabilidad recursiva: sus valores dependen "
            "de cuánto histórico se use"
        )

    # ── Veredicto ──
    if leak:
        verdict = VERDICT_OVERFIT
    elif score >= 70:
        verdict = VERDICT_ROBUST
    elif score >= 45:
        verdict = VERDICT_FRAGILE
    else:
        verdict = VERDICT_OVERFIT

    explanation = _build_explanation(verdict, score, reasons, strengths)

    return {
        "robustness_score": score,
        "verdict": verdict,
        "explanation": explanation,
        "reasons": reasons,
        "strengths": strengths,
        "component_scores": {k: int(round(v * 100)) for k, v in components.items()},
    }


def _build_explanation(verdict: str, score: int, reasons: list[str], strengths: list[str]) -> str:
    if verdict == VERDICT_ROBUST:
        text = f"La estrategia supera los controles de robustez con {score}/100. "
        if strengths:
            text += "Destaca por " + " y ".join(strengths[:2]) + ". "
        text += "Aun así, el rendimiento pasado no garantiza resultados futuros."
        return text

    if verdict == VERDICT_FRAGILE:
        text = f"La estrategia muestra señales mixtas ({score}/100). "
        if reasons:
            text += "El punto débil principal: " + reasons[0] + ". "
        text += "Conviene validarla con más datos y activos antes de arriesgar capital."
        return text

    # SOBREAJUSTADA
    text = f"La estrategia probablemente está sobreajustada ({score}/100). "
    if reasons:
        text += "Problema principal: " + reasons[0] + ". "
        if len(reasons) > 1:
            text += reasons[1].capitalize() + ". "
    text += "No es recomendable operarla con dinero real tal cual."
    return text
