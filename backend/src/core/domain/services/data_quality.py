"""
data_quality.py — Salud del almacén histórico OHLCV.

Puntúa la calidad de cada serie (símbolo+marco) del almacén propio a partir de
su cobertura y frescura: completitud (velas presentes frente a las esperadas),
antigüedad de la última vela y un estado legible. Dominio puro: recibe los
números ya calculados (cobertura + timestamps) y devuelve la evaluación.
"""

from __future__ import annotations

from typing import Optional


def series_health(*, candles: int, missing_candles: int, last_ms: Optional[int],
                  now_ms: int, step_ms: Optional[int]) -> dict:
    """Evalúa una serie: completitud, frescura y estado."""
    expected = candles + missing_candles
    completeness = round(candles / expected * 100.0, 1) if expected else 0.0

    age_ms = (now_ms - last_ms) if last_ms else None
    freshness_hours = round(age_ms / 3_600_000, 1) if age_ms is not None else None
    fresh = bool(age_ms is not None and step_ms and age_ms <= 2 * step_ms)

    if candles == 0:
        status = "VACIO"
    elif not fresh:
        status = "DESACTUALIZADO"
    elif missing_candles > 0:
        status = "CON_HUECOS"
    else:
        status = "SANO"

    return {
        "completeness_pct": completeness,
        "freshness_hours": freshness_hours,
        "fresh": fresh,
        "status": status,
    }


def overall_health(series: list[dict]) -> dict:
    """Resumen del almacén a partir de las series ya evaluadas."""
    n = len(series)
    if n == 0:
        return {"series": 0, "healthy_pct": 0.0, "with_gaps": 0, "stale": 0,
                "total_candles": 0, "grade": "SIN_DATOS"}

    healthy = sum(1 for s in series if s["status"] == "SANO")
    with_gaps = sum(1 for s in series if s["status"] == "CON_HUECOS")
    stale = sum(1 for s in series if s["status"] in ("DESACTUALIZADO", "VACIO"))
    total_candles = sum(s.get("candles", 0) for s in series)
    healthy_pct = round(healthy / n * 100.0, 1)

    if healthy_pct >= 90.0:
        grade = "EXCELENTE"
    elif healthy_pct >= 70.0:
        grade = "ACEPTABLE"
    else:
        grade = "DEFICIENTE"

    return {
        "series": n,
        "healthy_pct": healthy_pct,
        "with_gaps": with_gaps,
        "stale": stale,
        "total_candles": total_candles,
        "grade": grade,
    }
