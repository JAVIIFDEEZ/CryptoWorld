"""
get_price_structure.py — Caso de uso: soportes/resistencias y divergencias.

Trae el OHLCV del activo, detecta los niveles de soporte/resistencia por
agrupación de pivotes (fuerza = nº de toques) y las divergencias RSI/precio
recientes. La combinación es accionable: una divergencia bajista JUNTO a una
resistencia fuerte es una señal mucho más rica que cualquiera por separado.
"""

import logging

logger = logging.getLogger(__name__)

_LIMIT = 400


class GetPriceStructureUseCase:
    """Niveles S/R + divergencias RSI/precio de un activo en un marco."""

    def execute(self, asset_symbol: str, interval: str = "1h") -> dict:
        import ta as ta_lib
        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
        from core.domain.services.price_structure import detect_divergences, support_resistance

        symbol = (asset_symbol or "").upper().strip()
        if not symbol:
            return {"error": "Falta el símbolo del activo."}

        result = fetch_ohlcv_dataframe(symbol=symbol, interval=interval, limit=_LIMIT)
        if result is None or result.df.empty or len(result.df) < 60:
            return {"error": f"Datos insuficientes para {symbol} en {interval}."}
        df = result.df

        high = df["high"].to_numpy(dtype=float)
        low = df["low"].to_numpy(dtype=float)
        close = df["close"].to_numpy(dtype=float)
        last_price = float(close[-1])

        levels = support_resistance(high, low, close)
        rsi = ta_lib.momentum.RSIIndicator(df["close"], window=14).rsi().to_numpy(dtype=float)
        divergences = detect_divergences(close, rsi, lookback=80)

        supports = [lv for lv in levels if lv["kind"] == "support"]
        resistances = [lv for lv in levels if lv["kind"] == "resistance"]
        nearest_support = max(supports, key=lambda lv: lv["price"], default=None)
        nearest_resistance = min(resistances, key=lambda lv: lv["price"], default=None)

        return {
            "asset_symbol": symbol,
            "interval": interval,
            "last_price": last_price,
            "levels": levels,
            "nearest_support": nearest_support,
            "nearest_resistance": nearest_resistance,
            "divergences": divergences,
            "candles_analyzed": len(df),
            "data_source": result.source,
            "note": "Niveles por agrupación de pivotes (fuerza = nº de toques); divergencias "
                    "RSI/precio sobre los dos últimos pivotes. No constituye consejo financiero.",
        }
