"""
use_cases/get_fx_rates.py — Tasas de cambio fiat para conversión de precios.

Todos los precios del sistema se almacenan en USD. Este caso de uso expone
las tasas USD→EUR/GBP para que el frontend muestre los precios en la moneda
preferida del usuario sin duplicar datos en la BD.

Fuente: CoinGecko /exchange_rates (tasas con base BTC; el cociente entre
dos monedas da la tasa fiat-fiat). Si la API falla se devuelven tasas
estáticas aproximadas marcadas como source="fallback" para no romper la UI.
"""

import logging
from datetime import UTC, datetime

from core.infrastructure.external_apis.coingecko_client import (
    CoinGeckoClient,
    CoinGeckoClientError,
)

logger = logging.getLogger(__name__)

# Tasas aproximadas usadas solo si CoinGecko no responde
_FALLBACK_RATES = {"usd": 1.0, "eur": 0.92, "gbp": 0.79}

SUPPORTED_CURRENCIES = ("usd", "eur", "gbp")


class GetFxRatesUseCase:
    """Devuelve las tasas de conversión desde USD a las monedas soportadas."""

    def execute(self) -> dict:
        try:
            data = CoinGeckoClient().get_exchange_rates()
            rates = data.get("rates", {})
            usd_value = float(rates["usd"]["value"])
            result = {
                currency: round(float(rates[currency]["value"]) / usd_value, 6)
                for currency in SUPPORTED_CURRENCIES
                if currency in rates
            }
            # USD siempre presente y exacto
            result["usd"] = 1.0
            return {
                "base": "usd",
                "rates": result,
                "source": "coingecko",
                "updated_at": datetime.now(UTC).isoformat(),
            }
        except (CoinGeckoClientError, KeyError, TypeError, ValueError) as exc:
            logger.warning("FX rates no disponibles desde CoinGecko (%s); usando fallback.", exc)
            return {
                "base": "usd",
                "rates": dict(_FALLBACK_RATES),
                "source": "fallback",
                "updated_at": datetime.now(UTC).isoformat(),
            }
