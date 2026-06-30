"""
get_mtf_confluence.py — Caso de uso: confluencia multi-marco temporal (MTF).

Práctica profesional estándar (análisis multi-timeframe, p. ej. la triple
pantalla de Elder): una señal vale más cuando varios marcos temporales apuntan
en la misma dirección. Este caso de uso calcula el panel de señales
multi-indicador en varios marcos (15m, 1h, 4h, 1d), normaliza el score de cada
uno y produce:

  · alignment_score ∈ [-1, +1]: media PONDERADA de los scores normalizados,
    donde los marcos altos pesan más (1d > 4h > 1h > 15m) porque la tendencia
    de fondo manda sobre el ruido intradía.
  · agreement_pct: % de marcos que apuntan en la dirección dominante — mide si
    los marcos están de acuerdo, independientemente de la intensidad.
  · verdict honesto: ALINEADO solo cuando dirección clara Y acuerdo alto;
    MIXTO cuando los marcos se contradicen (la situación más peligrosa para
    operar) y NEUTRAL cuando no hay dirección.
"""

import logging

logger = logging.getLogger(__name__)

# Marcos analizados y su peso (la tendencia de fondo pesa más que el intradía).
MTF_FRAMES: list[tuple[str, float]] = [
    ("15m", 1.0),
    ("1h", 2.0),
    ("4h", 3.0),
    ("1d", 4.0),
]

_CANDLES_PER_FRAME = 300

# Umbrales del veredicto (sobre alignment_score y agreement_pct).
_ALIGN_MIN = 0.15     # dirección mínima para no ser NEUTRAL
_AGREE_MIN = 75.0     # % de acuerdo mínimo para considerar los marcos ALINEADOS


class GetMtfConfluenceUseCase:
    """Señales multi-indicador en varios marcos + puntuación de alineación."""

    def execute(self, asset_symbol: str) -> dict:
        from core.application.use_cases.ohlcv_fetcher import fetch_ohlcv_dataframe
        from core.domain.services.technical_analysis_service import calculate_signals_dashboard

        symbol = (asset_symbol or "").upper().strip()
        if not symbol:
            return {"error": "Falta el símbolo del activo."}

        frames = []
        for interval, weight in MTF_FRAMES:
            entry: dict = {"interval": interval, "weight": weight}
            try:
                result = fetch_ohlcv_dataframe(symbol=symbol, interval=interval, limit=_CANDLES_PER_FRAME)
                if result is None or result.df.empty or len(result.df) < 50:
                    entry["error"] = "Datos insuficientes."
                    frames.append(entry)
                    continue
                dash = calculate_signals_dashboard(result.df)
            except Exception as exc:  # noqa: BLE001 — un marco caído no tumba el análisis
                logger.warning("mtf %s/%s: %s", symbol, interval, exc)
                entry["error"] = str(exc)
                frames.append(entry)
                continue

            summary = dash.get("summary", {})
            total = int(summary.get("total", 0))
            score = float(summary.get("score", 0))
            max_score = total * 2 if total else 0
            normalized = round(score / max_score, 4) if max_score else 0.0
            entry.update({
                "verdict": summary.get("verdict", "NEUTRAL"),
                "score": score,
                "max_score": max_score,
                "normalized": normalized,          # ∈ [-1, +1]
                "buy_count": summary.get("buy_count", 0),
                "neutral_count": summary.get("neutral_count", 0),
                "sell_count": summary.get("sell_count", 0),
                "last_price": dash.get("last_price"),
            })
            frames.append(entry)

        valid = [f for f in frames if "error" not in f]
        if not valid:
            return {"error": f"No hay datos de mercado suficientes para {symbol} en ningún marco."}

        # Alineación ponderada: los marcos altos definen la dirección de fondo.
        total_weight = sum(f["weight"] for f in valid)
        alignment = sum(f["normalized"] * f["weight"] for f in valid) / total_weight

        # Acuerdo direccional: % de marcos que apuntan como la dirección dominante.
        direction = 1 if alignment > 0 else (-1 if alignment < 0 else 0)
        if direction != 0:
            agreeing = sum(1 for f in valid if (f["normalized"] > 0) == (direction > 0) and f["normalized"] != 0)
            agreement_pct = round(agreeing / len(valid) * 100.0, 1)
        else:
            agreement_pct = 0.0

        verdict, verdict_text = self._verdict(alignment, agreement_pct, len(valid))

        return {
            "asset_symbol": symbol,
            "frames": frames,
            "frames_analyzed": len(valid),
            "alignment_score": round(alignment, 4),
            "agreement_pct": agreement_pct,
            "verdict": verdict,
            "verdict_text": verdict_text,
            "disclaimer": "Confluencia de indicadores en varios marcos temporales. "
                          "No constituye consejo financiero.",
        }

    @staticmethod
    def _verdict(alignment: float, agreement_pct: float, n_frames: int) -> tuple[str, str]:
        if abs(alignment) < _ALIGN_MIN:
            return "NEUTRAL", (
                "Sin dirección clara: los indicadores están cerca del equilibrio "
                "en el conjunto de marcos temporales."
            )
        side = "ALCISTA" if alignment > 0 else "BAJISTA"
        if agreement_pct >= _AGREE_MIN:
            return f"ALINEADO_{side}", (
                f"Confluencia {side.lower()}: {agreement_pct:.0f}% de los {n_frames} marcos "
                f"apuntan en la misma dirección — la señal intradía va a favor de la tendencia de fondo."
            )
        return "MIXTO", (
            f"Marcos en conflicto: la dirección dominante es {side.lower()} pero solo "
            f"{agreement_pct:.0f}% de los marcos la acompañan. Operar contra marcos "
            f"superiores es la situación de mayor riesgo."
        )
