"""
get_address_dossier.py — Dossier forense unificado de una dirección.

El capstone del submódulo forense: un ÚNICO informe de auditoría que reúne las
herramientas orientadas a direcciones —puntuación de riesgo, huella conductual,
aprobaciones ERC-20 vivas, grafo de entidad y rastreo de flujos— y las sintetiza
en un veredicto global con los hallazgos clave. Es el documento que un desk de
cumplimiento imprime para el comité (patrón del dossier de estrategia).

Orquesta los casos de uso ya existentes (cada uno cacheado y con degradación
honesta): si una sección no está disponible, el dossier se emite igualmente con
el resto. Un cliente Blockscout compartido evita reconstruir la sesión HTTP.
"""

import logging

from core.infrastructure.external_apis.blockscout_client import (
    BlockscoutClient, is_valid_address,
)

logger = logging.getLogger(__name__)

_CACHE_TTL = 900  # 15 min

# Bandas del veredicto global (score 0-100 → etiqueta).
_BANDS = (("CRÍTICO", 70), ("ELEVADO", 45), ("MODERADO", 25), ("LIMPIO", 0))

# Aportación extra al score global por la peor aprobación viva.
_APPROVAL_BUMP = {"SEVERO": 30, "ALTO": 18, "MEDIO": 6, "BAJO": 0, "NINGUNO": 0}


def _band(score: float) -> str:
    for name, threshold in _BANDS:
        if score >= threshold:
            return name
    return "LIMPIO"


class AddressDossierUseCase:
    """Informe forense unificado de una dirección con veredicto global."""

    def __init__(self, client=None):
        self._client = client or BlockscoutClient()

    def execute(self, chain: str, address: str) -> dict:
        if not is_valid_address(address):
            return {"error": "Dirección EVM no válida (esperado 0x + 40 hex)."}
        from django.core.cache import cache

        key = f"address_dossier:{chain}:{address.lower()}"
        cached = cache.get(key)
        if cached is not None:
            return cached

        from core.application.use_cases.get_onchain_risk import (
            AddressRiskUseCase, ApprovalsUseCase, EntityGraphUseCase,
        )
        from core.application.use_cases.get_onchain_forensics import (
            TraceFlowUseCase, WalletFingerprintUseCase,
        )

        c = self._client
        risk = AddressRiskUseCase(client=c).execute(chain, address)
        fingerprint = WalletFingerprintUseCase(client=c).execute(chain, address)
        approvals = ApprovalsUseCase(client=c).execute(chain, address)
        entity = EntityGraphUseCase(client=c).execute(chain, address)
        flow = TraceFlowUseCase(client=c).execute(chain, address, depth=2)

        verdict = self._synthesize(risk, approvals, flow, fingerprint, entity)
        result = {
            "status": "OK",
            "chain": chain,
            "address": address.lower(),
            "verdict": verdict,
            "sections": {
                "risk": risk if not risk.get("error") else {"available": False, "error": risk.get("error")},
                "fingerprint": fingerprint if not fingerprint.get("error") else {"available": False},
                "approvals": approvals if not approvals.get("error") else {"available": False},
                "entity": entity if not entity.get("error") else {"available": False},
                "flow": flow if not flow.get("error") else {"available": False},
            },
            "note": ("Dossier forense unificado: síntesis heurística de riesgo, conducta, "
                     "aprobaciones, entidad y flujos sobre datos públicos. Señala capacidades "
                     "y patrones, no atribución de identidad ni consejo legal/financiero."),
        }
        cache.set(key, result, _CACHE_TTL)
        return result

    @staticmethod
    def _synthesize(risk, approvals, flow, fingerprint, entity) -> dict:
        """Veredicto global + hallazgos clave a partir de las secciones."""
        findings: list[dict] = []

        risk_score = risk.get("score", 0) if not risk.get("error") else 0
        risk_band = risk.get("band") if not risk.get("error") else None
        if risk_band in ("ALTO", "SEVERO"):
            findings.append({"severity": "high", "text":
                             f"Riesgo de dirección {risk_band} ({risk_score}/100)."})
        for f in (risk.get("factors") or [])[:2]:
            if f.get("kind") in ("self", "counterparty"):
                findings.append({"severity": "high", "text": f.get("detail", "")})

        worst_approval = approvals.get("worst", "NINGUNO") if not approvals.get("error") else "NINGUNO"
        if worst_approval in ("SEVERO", "ALTO"):
            findings.append({"severity": "high" if worst_approval == "SEVERO" else "medium",
                             "text": f"Aprobación ERC-20 viva de riesgo {worst_approval} "
                                     f"({approvals.get('unlimited', 0)} ilimitadas)."})

        for p in (flow.get("patterns") or []) if not flow.get("error") else []:
            findings.append({"severity": "medium", "text": p.get("note", p.get("type"))})

        if not fingerprint.get("error"):
            fp = fingerprint.get("fingerprint", {})
            if fp.get("available") and fp.get("archetype") in ("Distribuidora", "Bot / automatizada"):
                findings.append({"severity": "info",
                                 "text": f"Conducta: {fp['archetype']}."})

        if not entity.get("error") and entity.get("entity_size", 1) > 1:
            findings.append({"severity": "info",
                             "text": f"Entidad probable de {entity['entity_size']} direcciones "
                                     f"vinculadas por co-movimiento."})

        # Score global: riesgo de dirección + refuerzo por aprobaciones peligrosas.
        overall = min(100, risk_score + _APPROVAL_BUMP.get(worst_approval, 0))
        band = _band(overall)
        headline = {
            "CRÍTICO": "Múltiples señales graves: tratar con máxima cautela.",
            "ELEVADO": "Señales de riesgo relevantes que conviene revisar.",
            "MODERADO": "Algunas señales a vigilar; nada concluyente.",
            "LIMPIO": "Sin señales de riesgo destacables en la muestra analizada.",
        }[band]

        sev_order = {"high": 0, "medium": 1, "info": 2}
        findings.sort(key=lambda f: sev_order.get(f["severity"], 9))
        return {
            "overall_score": overall,
            "band": band,
            "headline": headline,
            "risk_band": risk_band,
            "worst_approval": worst_approval,
            "key_findings": findings,
        }
