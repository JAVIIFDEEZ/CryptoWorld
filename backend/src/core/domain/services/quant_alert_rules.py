"""
quant_alert_rules.py — Núcleo de dominio del motor de alertas cuantitativas.

Define el REGISTRO de métricas evaluables (metadatos: etiqueta, unidad,
categoría, ámbito activo/cartera) y la lógica pura de evaluación de una
condición con disparo por flanco (edge-trigger). No toca base de datos ni
servicios externos: recibe el valor ya calculado y el estado previo, y decide
si la alerta se dispara y cuál es el nuevo estado.

El disparo por flanco es lo que evita el spam: mientras el valor siga del
mismo lado del umbral, la alerta NO vuelve a dispararse; se re-arma sola al
cruzar de vuelta. El cooldown temporal se aplica en la capa de aplicación.
"""

from __future__ import annotations

from dataclasses import dataclass

# Operadores admitidos.
OPERATORS = ("gt", "lt", "cross_up", "cross_down")


@dataclass(frozen=True)
class MetricMeta:
    """Metadatos de una métrica evaluable por el motor de alertas."""

    key: str
    label: str
    unit: str
    category: str   # 'tecnica' | 'precio' | 'confluencia' | 'onchain' | 'riesgo'
    scope: str      # 'asset' | 'portfolio'
    hint: str = ""


# Registro único de métricas. La UI lo consume para pintar el constructor de
# reglas; los providers lo usan para saber qué calcular.
METRIC_REGISTRY: dict[str, MetricMeta] = {
    # ── Técnica (por activo + timeframe) ──────────────────────────────
    "rsi": MetricMeta("rsi", "RSI", "", "tecnica", "asset",
                      "0–100; sobreventa <30, sobrecompra >70"),
    "adx": MetricMeta("adx", "ADX", "", "tecnica", "asset",
                      "Fuerza de tendencia; >25 indica tendencia"),
    "stoch_rsi": MetricMeta("stoch_rsi", "StochRSI", "", "tecnica", "asset"),
    "macd_hist": MetricMeta("macd_hist", "MACD (histograma)", "", "tecnica", "asset"),
    "realized_vol": MetricMeta("realized_vol", "Volatilidad realizada", "%",
                               "tecnica", "asset", "Anualizada, ventana reciente"),
    "atr_pct": MetricMeta("atr_pct", "ATR", "%", "tecnica", "asset",
                          "Rango medio verdadero como % del precio"),
    "range_pos": MetricMeta("range_pos", "Posición en el rango", "%",
                            "tecnica", "asset", "0% mínimo del rango, 100% máximo"),
    # ── Precio ────────────────────────────────────────────────────────
    "price": MetricMeta("price", "Precio", "$", "precio", "asset"),
    "change_24h": MetricMeta("change_24h", "Cambio 24h", "%", "precio", "asset"),
    # ── Confluencia 360° ──────────────────────────────────────────────
    "confluence_score": MetricMeta("confluence_score", "Score de confluencia 360°",
                                   "", "confluencia", "asset",
                                   "-100 (bajista) a +100 (alcista)"),
    # ── On-chain ──────────────────────────────────────────────────────
    "onchain_net_flow": MetricMeta("onchain_net_flow", "Flujo neto on-chain", "$",
                                   "onchain", "asset",
                                   "Positivo = entra a exchanges (presión vendedora)"),
    "onchain_pressure": MetricMeta("onchain_pressure", "Presión on-chain", "",
                                   "onchain", "asset", "-100 a +100"),
    # ── Riesgo de cartera (ámbito libro completo) ─────────────────────
    "portfolio_var": MetricMeta("portfolio_var", "VaR de cartera", "%",
                                "riesgo", "portfolio", "Value at Risk histórico"),
    "portfolio_cvar": MetricMeta("portfolio_cvar", "CVaR de cartera", "%",
                                 "riesgo", "portfolio", "Expected Shortfall"),
    "portfolio_concentration": MetricMeta("portfolio_concentration",
                                          "Concentración (HHI)", "", "riesgo",
                                          "portfolio", "0 diversificada, 1 concentrada"),
    "portfolio_exposure": MetricMeta("portfolio_exposure", "Exposición total", "$",
                                     "riesgo", "portfolio"),
}


def metric_meta(key: str) -> MetricMeta | None:
    return METRIC_REGISTRY.get(key)


def is_portfolio_metric(key: str) -> bool:
    meta = METRIC_REGISTRY.get(key)
    return bool(meta and meta.scope == "portfolio")


def _side(value: float, threshold: float) -> str:
    """Lado del umbral en el que cae el valor."""
    return "above" if value >= threshold else "below"


@dataclass
class Evaluation:
    """Resultado de evaluar una condición contra un valor y el estado previo."""

    fired: bool
    new_side: str
    message: str = ""


def _fmt(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".") if v == v else "—"


def evaluate(*, metric: str, operator: str, threshold: float, value: float,
             prev_side: str) -> Evaluation:
    """
    Decide si una alerta se dispara, con disparo por flanco.

    - ``gt`` / ``lt``: nivel simple; dispara SOLO al entrar en la zona
      (transición de estado), no en cada evaluación mientras siga dentro.
    - ``cross_up`` / ``cross_down``: cruce explícito del umbral en la
      dirección indicada (requiere estado previo del lado contrario).

    Devuelve el nuevo lado para persistirlo y re-armar la alerta.
    """
    side = _side(value, threshold)
    meta = METRIC_REGISTRY.get(metric)
    label = meta.label if meta else metric
    unit = meta.unit if meta else ""

    fired = False
    if operator == "gt":
        fired = value >= threshold and prev_side != "above"
    elif operator == "lt":
        fired = value < threshold and prev_side != "below"
    elif operator == "cross_up":
        fired = prev_side == "below" and side == "above"
    elif operator == "cross_down":
        fired = prev_side == "above" and side == "below"

    message = ""
    if fired:
        symbol = {
            "gt": "≥", "lt": "<", "cross_up": "cruzó al alza",
            "cross_down": "cruzó a la baja",
        }.get(operator, operator)
        message = f"{label} {symbol} {_fmt(threshold)}{unit} — valor actual {_fmt(value)}{unit}"

    return Evaluation(fired=fired, new_side=side, message=message)
