"""
generation_power.py — ¿Tenía esta ejecución datos suficientes para juzgar?

El generador puede terminar sin ninguna estrategia por dos razones que **no se
parecen en nada**:

  1. **No hay edge.** Se probaron miles de configuraciones sobre un histórico
     amplio y ninguna sobrevivió. Es un resultado, y además el correcto.
  2. **No hay muestra.** El histórico era tan corto que las propias pruebas
     estadísticas no podían dar un veredicto. No se ha descubierto nada sobre el
     mercado; se ha descubierto que faltaban datos.

Hasta ahora el motor presentaba las dos igual —«ninguna estrategia superó el
gating de robustez… el mercado no ofrece un edge robusto»— y eso es una
**atribución falsa** en el segundo caso. Peor que no informar: informa mal, y
lleva al usuario a concluir que un activo no es operable cuando lo que pasa es
que se le pidieron 30 días de velas.

La unidad correcta son las OPERACIONES, no las velas
────────────────────────────────────────────────────
Un tramo de 116 velas suena razonable hasta que se ve que, en un marco de 1 h,
son cinco días, y que una estrategia que opera dos veces por semana produce ahí
**una operación**. El Sharpe de un tramo con una operación no es una medida
ruidosa: no es una medida. Y el percentil 5 de un Monte Carlo sobre ocho
operaciones tampoco.

Por eso el diagnóstico se expresa en operaciones por tramo, y por eso una
estrategia rechazada con muy pocas operaciones **no cuenta como evidencia en su
contra**.

Capa de dominio: Python puro.
"""

from __future__ import annotations

# Minutos por vela de cada marco soportado.
_INTERVAL_MINUTES: dict[str, int] = {
    "1m": 1, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360,
    "12h": 720, "1d": 1440, "1w": 10080,
}

# Operaciones por tramo walk-forward a partir de las cuales el Sharpe de ese
# tramo empieza a significar algo. No es un número mágico: por debajo de ~10
# operaciones el error estándar del Sharpe supera a su propia magnitud para
# cualquier edge realista, así que el fold no discrimina.
GOOD_TRADES_PER_FOLD = 10
MIN_TRADES_PER_FOLD = 4

# Operaciones totales por debajo de las cuales el Monte Carlo sobre la secuencia
# de trades no tiene con qué remuestrear.
MIN_TRADES_FOR_MONTE_CARLO = 30


def span_days(candles: int, interval: str) -> float:
    """Días de calendario que cubre un número de velas en un marco dado."""
    minutes = _INTERVAL_MINUTES.get(interval)
    if not minutes or candles <= 0:
        return 0.0
    return candles * minutes / 1440.0


def assess(candles: int, interval: str, wf_splits: int,
           trades_observed: int | None = None,
           evolution_candles: int | None = None) -> dict:
    """
    Evalúa si la ejecución tenía potencia estadística para dar un veredicto.

    `trades_observed` son las operaciones de la mejor candidata sobre la zona de
    evolución. Sin ese dato el diagnóstico se limita a la geometría (velas,
    tramos, días), que ya detecta el caso más común —marco corto con el límite
    de velas de un marco largo— pero no puede hablar de operaciones.
    """
    evo = evolution_candles or candles
    fold_bars = evo // (wf_splits + 1) if wf_splits > 0 else evo
    days = span_days(candles, interval)
    fold_days = span_days(fold_bars, interval)

    limits: list[str] = []
    reliability = "high"

    if days < 180:
        reliability = "low"
        limits.append(
            f"el histórico cubre solo {days:.0f} días: no incluye un ciclo de "
            "mercado completo, así que lo que sobreviva puede estar ajustado a "
            "un único régimen")
    if days < 60:
        reliability = "insufficient"

    trades_per_fold = None
    if trades_observed is not None and wf_splits > 0:
        trades_per_fold = trades_observed / (wf_splits + 1)
        if trades_per_fold < MIN_TRADES_PER_FOLD:
            reliability = "insufficient"
            limits.append(
                f"cada tramo walk-forward contiene ~{trades_per_fold:.1f} "
                "operaciones: el Sharpe de un tramo así no es una medida ruidosa, "
                "es que no es una medida")
        elif trades_per_fold < GOOD_TRADES_PER_FOLD:
            reliability = "insufficient" if reliability == "insufficient" else "low"
            limits.append(
                f"~{trades_per_fold:.1f} operaciones por tramo: por debajo de "
                f"{GOOD_TRADES_PER_FOLD} el error estándar del Sharpe supera a su "
                "propia magnitud y el tramo apenas discrimina")
        if trades_observed < MIN_TRADES_FOR_MONTE_CARLO:
            reliability = "insufficient"
            limits.append(
                f"{trades_observed} operaciones en total: el Monte Carlo remuestrea "
                "esa secuencia, y con menos de "
                f"{MIN_TRADES_FOR_MONTE_CARLO} su percentil 5 no distingue una "
                "estrategia mala de una con mala suerte")

    return {
        "candles": candles,
        "interval": interval,
        "span_days": round(days, 1),
        "evolution_candles": evo,
        "wf_splits": wf_splits,
        "bars_per_fold": fold_bars,
        "days_per_fold": round(fold_days, 1),
        "trades_observed": trades_observed,
        "trades_per_fold": round(trades_per_fold, 1) if trades_per_fold is not None else None,
        "reliability": reliability,      # high | low | insufficient
        "limits": limits,
        "note": _note(reliability, limits, days, interval),
    }


def _note(reliability: str, limits: list[str], days: float, interval: str) -> str:
    if reliability == "high":
        return (f"El histórico ({days:.0f} días en {interval}) da potencia "
                "suficiente: si no sobrevive ninguna estrategia, es un resultado "
                "sobre el mercado y no sobre la muestra.")
    head = ("Este veredicto NO es concluyente sobre el mercado."
            if reliability == "insufficient" else
            "Este veredicto es orientativo, no concluyente.")
    return head + " " + "; ".join(limits) + "."


def explains_empty_book(power: dict) -> bool:
    """
    ¿Puede la falta de datos explicar por sí sola un libro vacío?

    Es la pregunta que decide cómo se redacta el resultado. Si es cierta, decir
    «el mercado no ofrece un edge robusto» sería atribuir al mercado lo que
    causó el tamaño de la muestra.
    """
    return power.get("reliability") == "insufficient"


def recommended_candles(interval: str, target_days: float = 1000.0,
                        cap: int = 4000, floor: int = 300) -> int:
    """
    Velas a pedir para cubrir un objetivo de calendario en este marco.

    El motor pedía **730 velas para todos los marcos**, un número elegido cuando
    solo había gráficos diarios (730 = 2 años). En 1 h son 30 días, y de ahí
    salían tramos walk-forward de cinco días. Pedir por calendario en vez de por
    recuento es lo que arregla la raíz.

    El objetivo son ~1000 días (dos ciclos largos), que es lo mínimo para que lo
    que sobreviva no esté ajustado a un único régimen de mercado.

    El tope lo dicta el coste de la búsqueda, que es LINEAL en velas —medido:
    584 ≈ 4 min de evolución exhaustiva, 4000 ≈ 20 min, 8000 ≈ 37—. Un objetivo
    sin límite convertiría cada ejecución en una espera inaceptable.

    Este tope se subió a 14 000 mientras se creía que la búsqueda en dos fases
    (`block_sampling`) desacoplaba el coste de la longitud de la serie. La
    comprobación de esa idea salió NEGATIVA (correlación de rangos −0.38 con el
    orden del histórico completo), así que el tope vuelve a donde el coste
    manda. En los marcos cortos manda el tope y no el calendario, y el
    diagnóstico de potencia lo dice en vez de callarlo.
    """
    minutes = _INTERVAL_MINUTES.get(interval)
    if not minutes:
        return 730
    needed = int(target_days * 1440 / minutes)
    return max(floor, min(cap, needed))
