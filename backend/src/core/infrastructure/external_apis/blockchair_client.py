"""
blockchair_client.py — Adaptador para la API pública de Blockchair.

Blockchair ofrece estadísticas on-chain actuales (snapshot) para múltiples
blockchains sin autenticación. No proporciona series históricas en el plan
gratuito (peticiones de agregación devuelven HTTP 430).

Chains soportadas:
  BTC  → bitcoin
  ETH  → ethereum
  LTC  → litecoin
  DOGE → dogecoin
  BCH  → bitcoin-cash
  XRP  → ripple
  ADA  → cardano
  DOT  → polkadot
  XLM  → stellar
  XMR  → monero

Endpoint: GET https://api.blockchair.com/{chain}/stats
Docs: https://blockchair.com/api/docs

Rate limit: ~1440 req/día (1 req/min) sin API key.
Principio: Adapter Pattern (Arquitectura Hexagonal).
"""

import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

BLOCKCHAIR_BASE_URL = "https://api.blockchair.com"
REQUEST_TIMEOUT = 15  # segundos

_RETRY_STRATEGY = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
    raise_on_status=False,
)

# Mapeo símbolo interno → nombre de chain en Blockchair
CHAIN_MAP: dict[str, str] = {
    "BTC": "bitcoin",
    "ETH": "ethereum",
    "LTC": "litecoin",
    "DOGE": "dogecoin",
    "BCH": "bitcoin-cash",
    "XRP": "ripple",
    "ADA": "cardano",
    "DOT": "polkadot",
    "XLM": "stellar",
    "XMR": "monero",
}

SUPPORTED_SYMBOLS = list(CHAIN_MAP.keys())

# Campos comunes extraídos del snapshot de cada chain
# Cada campo: (clave_api, etiqueta_legible, unidad)
COMMON_FIELDS: list[tuple[str, str, str]] = [
    ("transactions_24h",              "Transacciones 24h",         "tx"),
    ("blocks_24h",                    "Bloques 24h",               "bloques"),
    ("difficulty",                    "Dificultad",                ""),
    ("hashrate_24h",                  "Hash Rate 24h",             "H/s"),
    ("mempool_transactions",          "Transacciones en Mempool",  "tx"),
    ("mempool_size",                  "Tamaño Mempool",            "bytes"),
    ("average_transaction_fee_usd_24h","Fee medio (USD)",          "USD"),
    ("median_transaction_fee_usd_24h", "Fee mediano (USD)",        "USD"),
    ("market_price_usd",              "Precio",                    "USD"),
    ("market_cap_usd",                "Market Cap",                "USD"),
    ("market_dominance_percentage",   "Dominancia",                "%"),
]

# Campos exclusivos de ETH
ETH_EXTRA_FIELDS: list[tuple[str, str, str]] = [
    ("burned_24h",                           "ETH quemado 24h",           "wei"),
    ("average_simple_transaction_fee_usd_24h","Fee simple medio (USD)",   "USD"),
]


class BlockchairClientError(Exception):
    """Error al comunicarse con la API de Blockchair."""


class BlockchairClient:
    """
    Cliente HTTP para Blockchair API (plan gratuito).

    Solo proporciona estadísticas actuales (snapshot), no series temporales.

    Uso:
        client = BlockchairClient()
        stats = client.get_stats("ETH")
    """

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({
            "Accept": "application/json",
            "User-Agent": "CryptoWorld/1.0",
        })
        adapter = HTTPAdapter(max_retries=_RETRY_STRATEGY)
        self._session.mount("https://", adapter)
        self._session.mount("http://", adapter)

    def get_stats(self, symbol: str) -> dict[str, Any]:
        """
        GET /{chain}/stats — Estadísticas actuales de la blockchain.

        Args:
            symbol: Símbolo de la moneda (BTC, ETH, LTC, …).

        Returns:
            Dict con las estadísticas actuales de la chain.

        Raises:
            BlockchairClientError: Si la chain no está soportada o hay
                                   error de red/rate limit.
        """
        symbol = symbol.upper()
        chain = CHAIN_MAP.get(symbol)
        if chain is None:
            raise BlockchairClientError(
                f"Chain '{symbol}' no soportada. "
                f"Disponibles: {SUPPORTED_SYMBOLS}"
            )

        try:
            resp = self._session.get(
                f"{BLOCKCHAIR_BASE_URL}/{chain}/stats",
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 430:
                raise BlockchairClientError(
                    "Rate limit de Blockchair alcanzado (HTTP 430). "
                    "Espera unos minutos antes de reintentar."
                )
            resp.raise_for_status()
            payload = resp.json()
            return payload.get("data", {})

        except requests.exceptions.Timeout:
            raise BlockchairClientError("Timeout al conectar con Blockchair.")
        except requests.exceptions.RequestException as exc:
            raise BlockchairClientError(f"Error de red: {exc}") from exc

    def get_supported_symbols(self) -> list[str]:
        """Devuelve la lista de símbolos soportados."""
        return SUPPORTED_SYMBOLS
