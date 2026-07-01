"""
strategy_portfolio.py — Caso de uso: cartera de estrategias campeonas.

Combina las mejores estrategias validadas (una por activo/marco) y analiza cómo
DIVERSIFICAN juntas: re-ejecuta el backtest de cada una sobre datos recientes
con costes realistas, convierte sus curvas de equity a retornos diarios (lo que
permite comparar marcos distintos), y calcula la matriz de correlación y las
métricas de la cartera equiponderada sobre las fechas comunes.

La lectura profesional: correlación media baja entre estrategias rentables =
diversificación real (drawdown conjunto menor que el de cada una por separado).
"""

import logging

logger = logging.getLogger(__name__)

_OHLCV_LIMIT = 500
_MAX_STRATEGIES = 6
_MIN_COMMON_DAYS = 5


class StrategyPortfolioUseCase:
    """Análisis de correlación y equity conjunta de las campeonas."""

    def execute(self, top_n: int = 5) -> dict:
        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
        from core.application.use_cases.reoptimize_strategies import BestStrategiesUseCase
        from core.domain.services.backtest_execution import simulate
        from core.domain.services.portfolio_analysis import (
            align_returns, avg_pairwise_correlation, correlation_matrix,
            daily_returns_from_equity, portfolio_stats,
        )
        from core.domain.services.strategy_evaluation import DEFAULT_COSTS
        from core.domain.services.strategy_spec import compile_signals, spec_risk, spec_sizing
        from core.infrastructure.persistence.models import StrategyDefinition

        top_n = min(max(int(top_n), 2), _MAX_STRATEGIES)
        champions = BestStrategiesUseCase().execute()["results"][:top_n]
        if len(champions) < 2:
            return {"error": "Se necesitan al menos 2 estrategias campeonas para analizar la cartera. "
                             "Genera estrategias para más activos."}

        series: dict[str, dict[str, float]] = {}
        members = []
        for champ in champions:
            strat = StrategyDefinition.objects.filter(id=champ["strategy_id"]).first()
            if strat is None:
                continue
            label = f"{champ['asset_symbol']} {champ['interval']}"
            try:
                res = fetch_ohlcv_dataframe(
                    symbol=champ["asset_symbol"], interval=champ["interval"], limit=_OHLCV_LIMIT,
                )
                if res is None or res.df.empty or len(res.df) < 60:
                    continue
                df = res.df
                signals = compile_signals(df, strat.spec)
                sim = simulate(
                    close=df["close"].to_numpy(dtype=float),
                    high=df["high"].to_numpy(dtype=float),
                    low=df["low"].to_numpy(dtype=float),
                    signals=signals,
                    costs=DEFAULT_COSTS,
                    risk=spec_risk(strat.spec),
                    sizing=spec_sizing(strat.spec),
                )
            except Exception as exc:  # noqa: BLE001 — una estrategia rota no tumba la cartera
                logger.warning("portfolio: %s falló: %s", label, exc)
                continue

            equity = sim.get("equity_curve") or []
            rets = daily_returns_from_equity(df["timestamp"].astype("int64").tolist(), equity)
            if not rets:
                continue
            series[label] = rets
            members.append({
                "strategy_id": strat.id,
                "label": label,
                "name": strat.name,
                "asset_symbol": champ["asset_symbol"],
                "interval": champ["interval"],
                "fitness": champ.get("fitness"),
                "window_return_pct": round((equity[-1] / equity[0] - 1.0) * 100.0, 2) if equity else None,
            })

        if len(series) < 2:
            return {"error": "No se pudieron re-ejecutar suficientes estrategias con datos actuales."}

        dates, aligned = align_returns(series)
        if len(dates) < _MIN_COMMON_DAYS:
            return {"error": f"Las estrategias solo comparten {len(dates)} días de datos: "
                             f"no hay ventana común suficiente para medir correlaciones."}

        names, matrix = correlation_matrix(aligned)
        stats = portfolio_stats(dates, aligned)
        avg_corr = avg_pairwise_correlation(matrix)

        return {
            "members": members,
            "labels": names,
            "correlation_matrix": matrix,
            "avg_correlation": avg_corr,
            "common_days": len(dates),
            "portfolio": stats,
            "note": "Cartera equiponderada sobre retornos diarios en la ventana común. "
                    "Correlación media baja entre estrategias rentables = diversificación real.",
        }
