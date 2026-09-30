"""
deribit_client.py — Adaptador para la API pública de Deribit (opciones).

Deribit concentra la práctica totalidad del volumen de opciones de BTC y ETH, y
su API v2 es **pública, gratuita y sin clave** para datos de mercado. Es el único
sitio del que se puede sacar una medida prospectiva de volatilidad de cripto sin
pagar un proveedor de datos.

URL base: https://www.deribit.com/api/v2

El endpoint que importa
───────────────────────
`/public/get_book_summary_by_currency?currency=BTC&kind=option` devuelve la cadena
ENTERA en una sola llamada: para cada instrumento su precio de marca, su
volatilidad implícita de marca y el precio del subyacente. Pedirlo instrumento a
instrumento serían cientos de llamadas para una foto que caduca en segundos.

Formato del nombre de instrumento: `BTC-27JUN25-100000-C`, es decir
`MONEDA-VENCIMIENTO-STRIKE-TIPO`. De ahí se saca todo lo necesario sin una
segunda llamada.

Dos conversiones de unidades que hay que hacer y que se hacen aquí
─────────────────────────────────────────────────────────────────
· Las primas se cotizan **en unidades del subyacente** (0,05 BTC), no en USD. El
  dominio trabaja en una sola moneda, así que se multiplican por el precio del
  subyacente.
· La volatilidad implícita viene **en porcentaje** (65,4), y el dominio la espera
  en fracción (0,654).

Hacerlas en el adaptador y no en el dominio es deliberado: son propiedades de
esta API concreta, y el día que se añada otra fuente de opciones el dominio no
tiene que enterarse.

Principio aplicado: Adapter Pattern (arquitectura hexagonal).
"""

from __future__ import annotations

import logging
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

DERIBIT_BASE_URL = "https://www.deribit.com/api/v2"
REQUEST_TIMEOUT = 20

_RETRY_STRATEGY = Retry(
    total=3,
    backoff_factor=0.6,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)


class DeribitClientError(RuntimeError):
    """Fallo al hablar con Deribit."""


class DeribitPublicClient:
    """Cliente de solo lectura para los datos de mercado de opciones."""

    def __init__(self, base_url: str = DERIBIT_BASE_URL):
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        adapter = HTTPAdapter(max_retries=_RETRY_STRATEGY)
        self._session.mount("https://", adapter)

    def option_book_summary(self, currency: str = "BTC") -> list[dict]:
        """
        GET /public/get_book_summary_by_currency — la cadena completa de opciones.

        Una sola llamada para todos los vencimientos y strikes. Cada fila trae
        `instrument_name`, `mark_price` (en unidades del subyacente), `mark_iv`
        (en porcentaje) y `underlying_price`.
        """
        datos = self._get("/public/get_book_summary_by_currency",
                          {"currency": currency.upper(), "kind": "option"})
        return datos if isinstance(datos, list) else []

    def index_price(self, currency: str = "BTC") -> float | None:
        """GET /public/get_index_price — precio del índice del subyacente."""
        datos = self._get("/public/get_index_price",
                          {"index_name": f"{currency.lower()}_usd"})
        if isinstance(datos, dict):
            valor = datos.get("index_price")
            return float(valor) if valor is not None else None
        return None

    def ping(self) -> bool:
        try:
            self._get("/public/get_time")
            return True
        except DeribitClientError:
            return False

    # ── Internos ───────────────────────────────────────────────────

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.get(url, params=params or {}, timeout=REQUEST_TIMEOUT)
            resp.raise_for_status()
            cuerpo = resp.json()
        except requests.RequestException as exc:
            logger.error("Deribit request error en %s: %s", path, exc)
            raise DeribitClientError(f"Error de red con Deribit: {exc}") from exc
        except ValueError as exc:
            raise DeribitClientError(f"Respuesta no JSON de Deribit: {exc}") from exc

        # La API envuelve todo en {"result": ...} y los errores en {"error": ...}.
        if isinstance(cuerpo, dict) and "error" in cuerpo:
            raise DeribitClientError(f"Deribit devolvió error: {cuerpo['error']}")
        if isinstance(cuerpo, dict) and "result" in cuerpo:
            return cuerpo["result"]
        return cuerpo


def parse_instrument(name: str) -> dict | None:
    """
    Descompone `BTC-27JUN25-100000-C` en sus partes.

    Devuelve None ante cualquier formato que no encaje, en lugar de adivinar: un
    instrumento mal leído entra en la cadena con un strike equivocado y contamina
    la integral entera sin que nada falle de forma visible.
    """
    from datetime import datetime, timezone as _tz

    partes = (name or "").split("-")
    if len(partes) != 4:
        return None
    moneda, vencimiento, strike, tipo = partes
    if tipo not in ("C", "P"):
        return None
    try:
        strike_f = float(strike)
        # Deribit vence a las 08:00 UTC.
        fecha = datetime.strptime(vencimiento, "%d%b%y").replace(
            hour=8, tzinfo=_tz.utc)
    except (ValueError, TypeError):
        return None
    if strike_f <= 0:
        return None
    return {"currency": moneda.upper(), "expiry": fecha, "strike": strike_f,
            "is_call": tipo == "C"}
