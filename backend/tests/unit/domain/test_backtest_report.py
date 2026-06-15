"""
tests/unit/domain/test_backtest_report.py — Veredicto de robustez.

Prueba la lógica de scoring con diccionarios de diagnóstico construidos:
un caso robusto → ROBUSTA, uno sobreajustado → SOBREAJUSTADA, y la fuga del
futuro fuerza SOBREAJUSTADA con puntuación mínima.
"""

import pytest

from core.domain.services.backtest_report import (
    VERDICT_FRAGILE,
    VERDICT_OVERFIT,
    VERDICT_ROBUST,
    build_robustness_report,
)


def _clean_bias():
    return {
        "lookahead": {"is_leaky": False},
        "recursive_instability": {"is_unstable": False},
    }


def _robust_diagnostics():
    return {
        "pbo": {"pbo": 0.05},
        "deflated_sharpe": {"dsr": 0.9},
        "walk_forward_rolling": {"efficiency": 0.85, "mean_oos_sharpe": 1.2},
        "walk_forward_anchored": {"efficiency": 0.9, "mean_oos_sharpe": 1.4},
        "monte_carlo": {"prob_profit_pct": 88.0},
        "permutation": {"p_value": 0.01},
        **_clean_bias(),
    }


def _overfit_diagnostics():
    return {
        "pbo": {"pbo": 0.85},
        "deflated_sharpe": {"dsr": 0.1},
        "walk_forward_rolling": {"efficiency": 0.2, "mean_oos_sharpe": -0.3},
        "walk_forward_anchored": {"efficiency": 0.1, "mean_oos_sharpe": -0.5},
        "monte_carlo": {"prob_profit_pct": 45.0},
        "permutation": {"p_value": 0.6},
        **_clean_bias(),
    }


class TestVerdict:

    @pytest.mark.unit
    def test_robust_case_is_robusta(self):
        report = build_robustness_report(_robust_diagnostics())
        assert report["verdict"] == VERDICT_ROBUST
        assert report["robustness_score"] >= 70
        assert report["strengths"]

    @pytest.mark.unit
    def test_overfit_case_is_sobreajustada(self):
        report = build_robustness_report(_overfit_diagnostics())
        assert report["verdict"] == VERDICT_OVERFIT
        assert report["robustness_score"] < 45
        assert report["reasons"]

    @pytest.mark.unit
    def test_high_pbo_caps_below_robust(self):
        diag = _robust_diagnostics()
        diag["pbo"] = {"pbo": 0.6}  # PBO alto pese a buen resto
        report = build_robustness_report(diag)
        assert report["verdict"] != VERDICT_ROBUST

    @pytest.mark.unit
    def test_lookahead_leak_forces_overfit_and_low_score(self):
        diag = _robust_diagnostics()
        diag["lookahead"] = {"is_leaky": True}
        report = build_robustness_report(diag)
        assert report["verdict"] == VERDICT_OVERFIT
        assert report["robustness_score"] <= 15
        assert any("lookahead" in r or "futura" in r for r in report["reasons"])

    @pytest.mark.unit
    def test_explanation_is_spanish_nonempty(self):
        report = build_robustness_report(_robust_diagnostics())
        assert len(report["explanation"].split()) >= 8
        assert "asesoramiento financiero" in report["explanation"] or "resultados futuros" in report["explanation"]

    @pytest.mark.unit
    def test_mixed_case_can_be_fragile(self):
        diag = _robust_diagnostics()
        diag["deflated_sharpe"] = {"dsr": 0.45}
        diag["permutation"] = {"p_value": 0.08}
        diag["walk_forward_anchored"] = {"efficiency": 0.45, "mean_oos_sharpe": 0.3}
        diag["walk_forward_rolling"] = {"efficiency": 0.4, "mean_oos_sharpe": 0.2}
        diag["monte_carlo"] = {"prob_profit_pct": 60.0}
        diag["pbo"] = {"pbo": 0.35}
        report = build_robustness_report(diag)
        assert report["verdict"] in (VERDICT_FRAGILE, VERDICT_OVERFIT)
