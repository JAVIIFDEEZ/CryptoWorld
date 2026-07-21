"""
get_quant_snapshot.py — Caso de uso: terminal cuantitativa de un activo.

Obtiene OHLCV (Binance → KuCoin → CoinGecko o almacén propio) del activo y de
BTC en el mismo marco, y delega en el servicio de dominio quant_metrics el
cálculo del snapshot institucional (volatilidad, riesgo, régimen, beta…). Es la
capa de análisis técnico "estilo Bloomberg": una fotografía cuantitativa densa
que un profesional lee de un vistazo antes de operar.
"""

import logging

logger = logging.getLogger(__name__)

# 500 velas: suficientes para σ estable, ADX(14), medias de 50 y un rango amplio,
# sin castigar la latencia. El horizonte de 90 velas cabe holgado.
_CANDLES = 500


class GetQuantSnapshotUseCase:

    def execute(self, asset_symbol: str, interval: str = "1h") -> dict:
        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
        from core.domain.services.quant_metrics import compute_quant_snapshot

        symbol = (asset_symbol or "").upper().strip()
        interval = (interval or "1h").strip()
        if not symbol:
            return {"error": "Falta el símbolo del activo."}

        result = fetch_ohlcv_dataframe(symbol=symbol, interval=interval, limit=_CANDLES)
        if result is None or result.df.empty or len(result.df) < 30:
            return {"error": "Datos insuficientes para la terminal cuantitativa."}

        # BTC en el mismo marco para beta/correlación; best-effort (no bloquea).
        btc_df = None
        if symbol != "BTC":
            try:
                btc = fetch_ohlcv_dataframe(symbol="BTC", interval=interval, limit=_CANDLES)
                if btc is not None and not btc.df.empty:
                    btc_df = btc.df
            except Exception:  # noqa: BLE001 — sin BTC solo falta la beta
                btc_df = None

        snapshot = compute_quant_snapshot(
            result.df, interval=interval, btc_df=btc_df, symbol=symbol,
        )
        if snapshot.get("error"):
            return snapshot
        snapshot["data_source"] = result.source
        return snapshot
