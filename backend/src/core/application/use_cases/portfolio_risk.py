"""
portfolio_risk.py — Caso de uso: riesgo agregado del libro completo.

Reúne la exposición del usuario en sus TRES libros y la mide como un solo
riesgo, que es como un actor institucional ve su cartera:
  · Posiciones manuales (Position): LONG suma, SHORT resta, valoradas a mercado.
  · Paper trading (PaperTradingAccount): la posición abierta marcada a mercado.
  · Ejecución real: las unidades compradas en el exchange, tanto las espejadas
    por la promoción (live_base_position) como las de las órdenes manuales,
    reconstruidas desde la auditoría de órdenes reales.

Con la exposición firmada por activo, calcula (dominio portfolio_risk):
  · VaR/CVaR 1 día por simulación histórica sobre el almacén OHLCV propio.
  · Stress testing con los peores movimientos realmente observados.

Sin histórico suficiente para un activo, ese activo cuenta en la exposición
pero se excluye del VaR (se dice cuántos quedaron fuera) — honestidad antes que
un número inventado.
"""

import logging

from core.domain.services import portfolio_risk as risk

logger = logging.getLogger(__name__)

_HIST_DAYS = 365        # ventana de histórico para VaR/stress
_HIST_INTERVAL = "1d"


def _manual_live_units(owner) -> dict[str, float]:
    """Unidades base netas por símbolo de las órdenes MANUALES ejecutadas.

    Se reconstruyen desde la auditoría (compras − ventas) porque una orden
    manual no actualiza ninguna posición persistida. El resultado se acota a
    cero por abajo: la venta de un activo que ya se tenía en el exchange antes
    de usar la plataforma dejaría un neto negativo que no es una posición corta.
    """
    from core.infrastructure.persistence.models import LiveOrderRecord

    units: dict[str, float] = {}
    rows = (LiveOrderRecord.objects
            .filter(owner=owner, status="sent", account__isnull=True)
            .values_list("symbol", "side", "amount"))
    for symbol, side, amount in rows:
        base = (symbol or "").split("/")[0].upper()
        if not base:
            continue
        units[base] = units.get(base, 0.0) + (amount if side == "buy" else -amount)
    return {s: u for s, u in units.items() if u > 1e-12}


def _spot_price(symbol: str) -> float:
    """Último precio conocido del activo en el catálogo local (0.0 si no hay)."""
    from core.infrastructure.persistence.models import CryptoAsset

    asset = (CryptoAsset.objects
             .filter(symbol__iexact=symbol).only("current_price").first())
    return float(asset.current_price) if asset and asset.current_price else 0.0


class PortfolioRiskUseCase:

    def execute(self, owner) -> dict:
        exposures = self._aggregate_exposures(owner)          # {symbol: {...}}
        if not exposures:
            return {"status": "EMPTY", "exposures": [], "gross_usd": 0.0, "net_usd": 0.0,
                    "note": "Sin posiciones abiertas en ningún libro."}

        closes = self._load_history(list(exposures))          # {symbol: np.ndarray}
        exposure_usd = {s: e["net_usd"] for s, e in exposures.items()}

        # ── VaR/CVaR sobre los activos con histórico suficiente ──
        returns_by_symbol = {s: risk.daily_returns(c) for s, c in closes.items()
                             if c is not None and len(c) > 1}
        symbols, matrix = risk.align_returns_matrix(returns_by_symbol)
        exp_vector = [exposure_usd[s] for s in symbols]
        var = risk.historical_var_cvar(matrix, exp_vector) if symbols else {"status": "INSUFICIENTE", "days": 0}
        covered = set(symbols)

        # ── Stress testing (peores ventanas observadas) ──
        stress = risk.stress_scenarios(
            {s: c for s, c in closes.items() if c is not None},
            exposure_usd,
        )

        gross = sum(abs(v) for v in exposure_usd.values())
        net = sum(exposure_usd.values())
        rows = sorted(
            [{"symbol": s, **e, "in_var": s in covered} for s, e in exposures.items()],
            key=lambda r: abs(r["net_usd"]), reverse=True,
        )
        # Concentración: mayor exposición absoluta sobre el bruto (Herfindahl-lite).
        top_share = round(abs(rows[0]["net_usd"]) / gross * 100.0, 1) if gross > 0 else 0.0

        return {
            "status": "OK",
            "exposures": rows,
            "gross_usd": round(gross, 2),
            "net_usd": round(net, 2),
            "long_usd": round(sum(v for v in exposure_usd.values() if v > 0), 2),
            "short_usd": round(sum(v for v in exposure_usd.values() if v < 0), 2),
            "top_concentration_pct": top_share,
            "var": var,
            "var_symbols_excluded": [s for s in exposures if s not in covered],
            "stress": stress,
            "history_days": _HIST_DAYS,
            "note": (
                "Exposición firmada agregada de posiciones manuales, paper trading "
                "y ejecución real. VaR/CVaR 1 día por simulación histórica sobre el "
                "almacén propio (sin asumir normalidad); stress = peores movimientos "
                "realmente observados. No constituye consejo financiero."
            ),
        }

    # ── Agregación de exposición por los tres libros ────────────────

    @staticmethod
    def _aggregate_exposures(owner) -> dict:
        from core.infrastructure.persistence.models import (
            PaperTradingAccount, Position,
        )

        agg: dict[str, dict] = {}

        def _add(symbol: str, book: str, usd: float) -> None:
            if not symbol or abs(usd) < 1e-9:
                return
            e = agg.setdefault(symbol.upper(), {
                "net_usd": 0.0, "by_book": {"manual": 0.0, "paper": 0.0, "live": 0.0},
            })
            e["net_usd"] += usd
            e["by_book"][book] += usd

        # ── Posiciones manuales (LONG +, SHORT −), a mercado ──
        for p in (Position.objects.select_related("asset")
                  .filter(user=owner, status="OPEN")):
            price = float(p.asset.current_price or 0)
            qty = float(p.open_quantity or 0)
            sign = 1.0 if p.direction == "LONG" else -1.0
            _add(p.asset.symbol, "manual", sign * qty * price)

        # ── Paper trading + ejecución real (siempre largo) ──
        for a in PaperTradingAccount.objects.filter(owner=owner, is_active=True):
            price = float(a.last_price or 0)
            if a.units and price:
                _add(a.asset_symbol, "paper", float(a.units) * price)
            if a.live_enabled and a.live_base_position and price:
                _add(a.asset_symbol, "live", float(a.live_base_position) * price)

        # ── Ejecución real MANUAL ──
        # Las órdenes lanzadas a mano no cuelgan de ninguna cartera de paper,
        # así que su posición hay que reconstruirla desde la auditoría. Sin
        # esto el libro real quedaba incompleto y el límite de concentración
        # medía sobre una exposición menor que la verdadera.
        for symbol, units in _manual_live_units(owner).items():
            price = _spot_price(symbol)
            if units and price:
                _add(symbol, "live", units * price)

        for e in agg.values():
            e["net_usd"] = round(e["net_usd"], 2)
            e["by_book"] = {k: round(v, 2) for k, v in e["by_book"].items()}
        return agg

    @staticmethod
    def _load_history(symbols: list[str]) -> dict:
        """Cierres diarios de cada activo desde el almacén propio; si el almacén
        no cubre, cae al fetcher remoto. Devuelve {symbol: np.ndarray | None}."""
        import numpy as np
        from core.application.use_cases import ohlcv_store
        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe

        out: dict = {}
        for symbol in symbols:
            closes = None
            try:
                df = ohlcv_store.load_dataframe(symbol, _HIST_INTERVAL, _HIST_DAYS)
                if df is not None and len(df) >= risk.MIN_OVERLAP_DAYS:
                    closes = df["close"].to_numpy(dtype=float)
                else:
                    res = fetch_ohlcv_dataframe(symbol=symbol, interval=_HIST_INTERVAL, limit=_HIST_DAYS)
                    if res is not None and not res.df.empty:
                        closes = res.df["close"].to_numpy(dtype=float)
            except Exception as exc:  # noqa: BLE001 — un activo sin datos no rompe el riesgo
                logger.warning("portfolio_risk history %s: %s", symbol, exc)
            out[symbol] = closes if (closes is not None and len(closes) > 1) else None
        return out
