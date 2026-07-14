"""
blockscout_client.py — Adaptador para la API REST v2 de Blockscout.

Blockscout es un explorador de bloques open-source con instancias públicas por
red. Su API v2 (sin autenticación) permite analítica on-chain a nivel de
DIRECCIÓN: saldo nativo, cartera de tokens ERC-20 con su valoración en USD y el
historial de transacciones. Eleva el módulo de blockchain de "estadísticas de
red" a "explorador de wallets" multi-cadena con datos 100% reales.

Endpoints usados (base por red, p. ej. https://eth.blockscout.com):
  GET /api/v2/addresses/{address}                 → info de la dirección
  GET /api/v2/addresses/{address}/token-balances  → tokens ERC-20 (saldos)
  GET /api/v2/addresses/{address}/transactions     → transacciones

Docs: https://docs.blockscout.com/devs/apis/rest
Sin API key. Principio: Adapter Pattern (Arquitectura Hexagonal).
"""

import logging
import re
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT = 15  # segundos

_RETRY_STRATEGY = Retry(
    total=3,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
    raise_on_status=False,
)

# Redes soportadas: slug → (nombre, instancia Blockscout, símbolo nativo, chain_id).
# Todas son instancias públicas mantenidas por Blockscout. Los umbrales de gas
# (Gwei) clasifican el coste como barato/normal/caro de forma específica por red
# (en L2 el gas es órdenes de magnitud menor que en Ethereum mainnet).
CHAINS: dict[str, dict[str, Any]] = {
    "ethereum": {"name": "Ethereum", "base_url": "https://eth.blockscout.com", "native": "ETH", "chain_id": 1, "gas_cheap": 10.0, "gas_high": 30.0},
    "base":     {"name": "Base",     "base_url": "https://base.blockscout.com", "native": "ETH", "chain_id": 8453, "gas_cheap": 0.05, "gas_high": 0.5},
    "optimism": {"name": "Optimism", "base_url": "https://optimism.blockscout.com", "native": "ETH", "chain_id": 10, "gas_cheap": 0.05, "gas_high": 0.5},
    "arbitrum": {"name": "Arbitrum", "base_url": "https://arbitrum.blockscout.com", "native": "ETH", "chain_id": 42161, "gas_cheap": 0.1, "gas_high": 1.0},
    "gnosis":   {"name": "Gnosis",   "base_url": "https://gnosis.blockscout.com", "native": "xDAI", "chain_id": 100, "gas_cheap": 2.0, "gas_high": 10.0},
}

SUPPORTED_CHAINS = list(CHAINS.keys())

# Una dirección EVM: 0x seguido de 40 dígitos hexadecimales.
_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def is_valid_address(address: str) -> bool:
    """True si `address` tiene forma de dirección EVM (0x + 40 hex)."""
    return bool(address and _ADDRESS_RE.match(address.strip()))


class BlockscoutClientError(Exception):
    """Error al comunicarse con la API de Blockscout."""


class BlockscoutClient:
    """
    Cliente HTTP para la API REST v2 de Blockscout (multi-cadena, sin auth).

    Uso:
        client = BlockscoutClient()
        info = client.get_address("ethereum", "0x...")
        tokens = client.get_token_balances("ethereum", "0x...")
        txs = client.get_transactions("ethereum", "0x...")
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

    def _base_url(self, chain: str) -> str:
        meta = CHAINS.get(chain)
        if meta is None:
            raise BlockscoutClientError(
                f"Red '{chain}' no soportada. Disponibles: {SUPPORTED_CHAINS}"
            )
        return meta["base_url"]

    def _get(self, chain: str, path: str, params: dict | None = None) -> Any:
        base = self._base_url(chain)
        try:
            resp = self._session.get(f"{base}{path}", params=params or {}, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 404:
                raise BlockscoutClientError("Dirección no encontrada en esta red.")
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            raise BlockscoutClientError("Timeout al conectar con Blockscout.")
        except requests.exceptions.RequestException as exc:
            raise BlockscoutClientError(f"Error de red: {exc}") from exc

    def get_address(self, chain: str, address: str) -> dict[str, Any]:
        """GET /api/v2/addresses/{address} — info de la dirección (saldo nativo,
        si es contrato, ENS, tasa de cambio del nativo)."""
        data = self._get(chain, f"/api/v2/addresses/{address}")
        return data if isinstance(data, dict) else {}

    def get_token_balances(self, chain: str, address: str) -> list[dict[str, Any]]:
        """GET /api/v2/addresses/{address}/token-balances — lista plana de saldos
        de tokens (se filtran los ERC-20 en la capa de aplicación)."""
        data = self._get(chain, f"/api/v2/addresses/{address}/token-balances")
        return data if isinstance(data, list) else []

    def get_transactions(self, chain: str, address: str) -> list[dict[str, Any]]:
        """GET /api/v2/addresses/{address}/transactions — transacciones recientes
        (primera página)."""
        data = self._get(chain, f"/api/v2/addresses/{address}/transactions")
        if isinstance(data, dict):
            return data.get("items", []) or []
        return data if isinstance(data, list) else []

    def get_token_holders(self, chain: str, token: str, pages: int = 1) -> list[dict[str, Any]]:
        """GET /api/v2/tokens/{token}/holders — mayores tenedores de un token
        (para la radiografía de concentración)."""
        return self._paginated_items(chain, f"/api/v2/tokens/{token}/holders", pages=pages)

    def get_token_info(self, chain: str, token: str) -> dict[str, Any]:
        """GET /api/v2/tokens/{token} — metadatos del token (nombre, símbolo,
        decimales, nº total de tenedores, supply)."""
        data = self._get(chain, f"/api/v2/tokens/{token}")
        return data if isinstance(data, dict) else {}

    def get_smart_contract(self, chain: str, address: str) -> dict[str, Any]:
        """GET /api/v2/smart-contracts/{address} — código verificado, ABI, si es
        proxy y su implementación (para el análisis de seguridad de tokens).
        Devuelve {} si el contrato no está verificado (404)."""
        try:
            data = self._get(chain, f"/api/v2/smart-contracts/{address}")
        except BlockscoutClientError:
            return {}
        return data if isinstance(data, dict) else {}

    def get_chain_stats(self, chain: str) -> dict[str, Any]:
        """GET /api/v2/stats — salud de la red: precios de gas (Gwei), utilización,
        tiempo de bloque, precio del nativo y totales."""
        data = self._get(chain, "/api/v2/stats")
        return data if isinstance(data, dict) else {}

    def get_balance_history(self, chain: str, address: str) -> list[dict[str, Any]]:
        """GET /api/v2/addresses/{address}/coin-balance-history-by-day — serie
        diaria del saldo nativo (en unidades mínimas/wei)."""
        data = self._get(chain, f"/api/v2/addresses/{address}/coin-balance-history-by-day")
        if isinstance(data, dict):
            return data.get("items", []) or []
        return data if isinstance(data, list) else []

    def _paginated_items(self, chain: str, path: str, pages: int = 1,
                         params: dict | None = None) -> list[dict[str, Any]]:
        """Recorre hasta `pages` páginas de un endpoint paginado de Blockscout
        (sigue `next_page_params`) y acumula los `items`. Tolera errores de red
        tras la primera página: devuelve lo acumulado."""
        items: list = []
        next_params = dict(params or {})
        for page in range(max(1, pages)):
            try:
                data = self._get(chain, path, params=next_params)
            except BlockscoutClientError:
                if page == 0:
                    raise
                break
            if not isinstance(data, dict):
                break
            items.extend(data.get("items", []) or [])
            next_page = data.get("next_page_params")
            if not next_page:
                break
            next_params = next_page
        return items

    def get_recent_transactions(self, chain: str, pages: int = 2) -> list[dict[str, Any]]:
        """GET /api/v2/transactions — transacciones recientes de toda la cadena
        (para detectar grandes transferencias de la moneda nativa)."""
        return self._paginated_items(chain, "/api/v2/transactions", pages=pages)

    def get_recent_token_transfers(self, chain: str, pages: int = 2) -> list[dict[str, Any]]:
        """GET /api/v2/token-transfers — transferencias de tokens recientes de toda
        la cadena (para detectar grandes movimientos de ERC-20, p. ej. stablecoins)."""
        return self._paginated_items(chain, "/api/v2/token-transfers", pages=pages,
                                     params={"type": "ERC-20"})

    @staticmethod
    def supported_chains() -> list[dict[str, Any]]:
        """Lista de redes soportadas con su metadata para la UI."""
        return [
            {"slug": slug, "name": m["name"], "native": m["native"],
             "chain_id": m["chain_id"], "explorer_url": m["base_url"]}
            for slug, m in CHAINS.items()
        ]
