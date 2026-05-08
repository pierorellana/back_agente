import logging
from dataclasses import dataclass
from typing import Any

from app.application.ports.services.gemini_client import GeminiClientPort
from app.application.services.healthcare_catalog_service import CatalogRecord
from app.domain.errors import BusinessRuleError

logger = logging.getLogger("app.triage")

_SEVERITY_RANK = {
    "critical": 4,
    "high": 3,
    "urgent": 3,
    "medium": 2,
    "moderate": 2,
    "low": 1,
}


@dataclass(frozen=True)
class EmergencyMatch:
    detected: bool
    severity_level: str | None
    matched_keywords: list[str]
    specialty_page_id: str | None


@dataclass(frozen=True)
class SpecialtyInference:
    specialty_page_id: str
    specialty_id: str
    specialty_name: str
    symptom_summary: str
    specialty_reason: str
    ai_confidence: float | None
    matched_keywords: list[str]


class MedicalTriageService:
    def __init__(self, gemini_client: GeminiClientPort | None = None) -> None:
        self._gemini_client = gemini_client

    def evaluate_emergency(
        self,
        symptom_text: str,
        emergency_keywords: list[CatalogRecord],
    ) -> EmergencyMatch:
        normalized_text = _normalize_text(symptom_text)
        matched_records: list[tuple[int, CatalogRecord, str]] = []

        for record in emergency_keywords:
            phrase = str(record.properties.get("phrase") or "").strip()
            if not phrase:
                continue

            match_type = _normalize_text(record.properties.get("match_type") or "contains")
            normalized_phrase = _normalize_text(phrase)

            if _matches_phrase(normalized_text, normalized_phrase, match_type):
                severity = _normalize_text(record.properties.get("severity_level") or "low")
                matched_records.append(
                    (
                        _SEVERITY_RANK.get(severity, 0),
                        record,
                        phrase,
                    )
                )

        if not matched_records:
            return EmergencyMatch(
                detected=False,
                severity_level=None,
                matched_keywords=[],
                specialty_page_id=None,
            )

        matched_records.sort(key=lambda item: item[0], reverse=True)
        highest = matched_records[0][1]
        matched_keywords = [phrase for _, _, phrase in matched_records]

        return EmergencyMatch(
            detected=True,
            severity_level=str(highest.properties.get("severity_level") or ""),
            matched_keywords=matched_keywords,
            specialty_page_id=_first_relation_id(highest.properties.get("suggested_specialty")),
        )

    def infer_specialty(
        self,
        symptom_text: str,
        specialties_by_page_id: dict[str, CatalogRecord],
        symptom_specialty_maps: list[CatalogRecord],
    ) -> SpecialtyInference:
        specialties = [
            specialty
            for specialty in specialties_by_page_id.values()
            if (
                specialty.properties.get("specialty_id")
                and specialty.properties.get("specialty_name")
            )
        ]
        if not specialties:
            raise BusinessRuleError("No active specialties were found in Notion.")

        candidate_context = _build_candidate_context(
            symptom_text,
            specialties,
            symptom_specialty_maps,
        )
        if self._gemini_client is not None:
            try:
                return self._infer_specialty_with_gemini(
                    symptom_text=symptom_text,
                    specialties=specialties,
                    candidate_context=candidate_context,
                )
            except Exception as exc:
                logger.warning("triage_gemini_fallback reason=%s", exc)

        fallback = candidate_context[0] if candidate_context else None
        if fallback is None:
            selected = specialties[0]
            return SpecialtyInference(
                specialty_page_id=selected.page_id,
                specialty_id=str(selected.properties.get("specialty_id")),
                specialty_name=str(selected.properties.get("specialty_name")),
                symptom_summary="No hubo suficiente contexto para resumir el sintoma.",
                specialty_reason=(
                    "Se selecciono la primera especialidad activa como respaldo por "
                    "falta de senales suficientes."
                ),
                ai_confidence=None,
                matched_keywords=[],
            )

        return SpecialtyInference(
            specialty_page_id=fallback["page_id"],
            specialty_id=fallback["specialty_id"],
            specialty_name=fallback["specialty_name"],
            symptom_summary=f"Paciente reporta: {symptom_text.strip()}",
            specialty_reason=(
                "Se eligio por coincidencia directa con palabras clave del mapa de sintomas."
            ),
            ai_confidence=None,
            matched_keywords=fallback["matched_keywords"],
        )

    def generate_recommendation_explanation(
        self,
        *,
        patient_name: str | None,
        specialty_name: str,
        symptom_summary: str,
        emergency_detected: bool,
        hospital_name: str,
        in_network: bool,
        coverage_status: str | None,
        estimated_patient_payment: float,
        currency: str | None,
        comparison_reasons: list[str],
    ) -> str:
        fallback = _build_fallback_explanation(
            patient_name=patient_name,
            specialty_name=specialty_name,
            symptom_summary=symptom_summary,
            emergency_detected=emergency_detected,
            hospital_name=hospital_name,
            in_network=in_network,
            coverage_status=coverage_status,
            estimated_patient_payment=estimated_patient_payment,
            currency=currency,
            comparison_reasons=comparison_reasons,
        )
        if self._gemini_client is None:
            return fallback

        prompt = (
            "Actua como un asistente de orientacion medica administrativa para un hackathon. "
            "No diagnostiques. Redacta una explicacion breve en espanol, clara y natural, "
            "basada solo en los hechos proporcionados.\n\n"
            f"Paciente: {patient_name or 'Paciente'}\n"
            f"Resumen del sintoma: {symptom_summary}\n"
            f"Especialidad sugerida: {specialty_name}\n"
            f"Emergencia detectada: {'si' if emergency_detected else 'no'}\n"
            f"Hospital recomendado: {hospital_name}\n"
            f"Dentro de red: {'si' if in_network else 'no'}\n"
            f"Estado de cobertura: {coverage_status or 'no definido'}\n"
            f"Copago estimado: {_format_money(estimated_patient_payment, currency)}\n"
            f"Motivos estructurados: {', '.join(comparison_reasons)}\n\n"
            "Devuelve una explicacion corta, humana y accionable."
        )
        schema = {
            "type": "object",
            "properties": {
                "explanation": {
                    "type": "string",
                    "description": "Explicacion breve y clara en espanol.",
                }
            },
            "required": ["explanation"],
        }

        try:
            payload = self._gemini_client.generate_json(
                prompt=prompt,
                schema=schema,
                temperature=0.3,
            )
        except Exception as exc:
            logger.warning("triage_explanation_fallback reason=%s", exc)
            return fallback

        explanation = payload.get("explanation")
        if not isinstance(explanation, str) or not explanation.strip():
            return fallback
        return explanation.strip()

    def _infer_specialty_with_gemini(
        self,
        *,
        symptom_text: str,
        specialties: list[CatalogRecord],
        candidate_context: list[dict[str, Any]],
    ) -> SpecialtyInference:
        assert self._gemini_client is not None

        specialty_choices = [
            {
                "specialty_id": str(record.properties.get("specialty_id")),
                "specialty_name": str(record.properties.get("specialty_name")),
                "description": str(record.properties.get("description") or ""),
                "is_emergency_specialty": bool(
                    record.properties.get("is_emergency_specialty") or False
                ),
            }
            for record in specialties
        ]

        prompt = (
            "Eres un clasificador de orientacion medica administrativa para un hackathon.\n"
            "No diagnostiques ni inventes especialidades.\n"
            "Debes elegir exactamente una especialidad usando solo alguno de los "
            "specialty_id permitidos.\n\n"
            f"Texto del paciente: {symptom_text.strip()}\n\n"
            f"Especialidades permitidas: {specialty_choices}\n\n"
            f"Senales del mapa de sintomas: {candidate_context[:8]}\n\n"
            "Entrega un resumen muy corto del sintoma, el specialty_id elegido, "
            "el nombre de la especialidad, la razon y una confianza entre 0 y 1."
        )
        schema = {
            "type": "object",
            "properties": {
                "symptom_summary": {"type": "string"},
                "specialty_id": {"type": "string"},
                "specialty_name": {"type": "string"},
                "specialty_reason": {"type": "string"},
                "ai_confidence": {"type": "number"},
                "matched_keywords": {
                    "type": "array",
                    "items": {"type": "string"},
                },
            },
            "required": [
                "symptom_summary",
                "specialty_id",
                "specialty_name",
                "specialty_reason",
                "ai_confidence",
                "matched_keywords",
            ],
        }
        payload = self._gemini_client.generate_json(prompt=prompt, schema=schema, temperature=0.2)
        specialty_id = str(payload.get("specialty_id") or "").strip()
        if not specialty_id:
            raise BusinessRuleError("Gemini did not return a valid specialty_id.")

        specialty = next(
            (
                record
                for record in specialties
                if str(record.properties.get("specialty_id")) == specialty_id
            ),
            None,
        )
        if specialty is None:
            raise BusinessRuleError("Gemini returned a specialty_id that is not in the catalog.")

        confidence = payload.get("ai_confidence")
        if isinstance(confidence, (int, float)):
            confidence = max(0.0, min(1.0, float(confidence)))
        else:
            confidence = None

        matched_keywords = payload.get("matched_keywords")
        if not isinstance(matched_keywords, list):
            matched_keywords = []

        return SpecialtyInference(
            specialty_page_id=specialty.page_id,
            specialty_id=specialty_id,
            specialty_name=str(specialty.properties.get("specialty_name")),
            symptom_summary=str(
                payload.get("symptom_summary") or f"Paciente reporta: {symptom_text.strip()}"
            ),
            specialty_reason=str(
                payload.get("specialty_reason") or "Especialidad seleccionada por Gemini."
            ),
            ai_confidence=confidence,
            matched_keywords=[str(item) for item in matched_keywords if item],
        )


def _build_candidate_context(
    symptom_text: str,
    specialties: list[CatalogRecord],
    symptom_specialty_maps: list[CatalogRecord],
) -> list[dict[str, Any]]:
    normalized_text = _normalize_text(symptom_text)
    specialty_lookup = {record.page_id: record for record in specialties}
    candidates: dict[str, dict[str, Any]] = {}

    for mapping in symptom_specialty_maps:
        specialty_page_id = _first_relation_id(mapping.properties.get("specialty"))
        if not specialty_page_id or specialty_page_id not in specialty_lookup:
            continue

        matched_keywords: list[str] = []
        for keyword in mapping.properties.get("keywords") or []:
            normalized_keyword = _normalize_text(keyword)
            if normalized_keyword and normalized_keyword in normalized_text:
                matched_keywords.append(str(keyword))

        if not matched_keywords:
            continue

        specialty = specialty_lookup[specialty_page_id]
        score = float(mapping.properties.get("ai_weight") or 1.0)
        confidence_score = mapping.properties.get("confidence_score")
        if isinstance(confidence_score, (int, float)):
            score += float(confidence_score)

        existing = candidates.setdefault(
            specialty_page_id,
            {
                "page_id": specialty_page_id,
                "specialty_id": str(specialty.properties.get("specialty_id")),
                "specialty_name": str(specialty.properties.get("specialty_name")),
                "description": str(specialty.properties.get("description") or ""),
                "score": 0.0,
                "matched_keywords": [],
            },
        )
        existing["score"] += score
        existing["matched_keywords"].extend(matched_keywords)

    ordered_candidates = list(candidates.values())
    ordered_candidates.sort(
        key=lambda item: (
            -float(item["score"]),
            item["specialty_name"],
        )
    )

    if ordered_candidates:
        for item in ordered_candidates:
            item["matched_keywords"] = sorted(set(item["matched_keywords"]))
        return ordered_candidates

    return [
        {
            "page_id": specialty.page_id,
            "specialty_id": str(specialty.properties.get("specialty_id")),
            "specialty_name": str(specialty.properties.get("specialty_name")),
            "description": str(specialty.properties.get("description") or ""),
            "score": 0.0,
            "matched_keywords": [],
        }
        for specialty in specialties
    ]


def _matches_phrase(text: str, phrase: str, match_type: str) -> bool:
    if not phrase:
        return False
    if match_type == "exact":
        return text == phrase
    return phrase in text


def _first_relation_id(value: Any) -> str | None:
    if not isinstance(value, list) or not value:
        return None
    first = value[0]
    return str(first) if first else None


def _build_fallback_explanation(
    *,
    patient_name: str | None,
    specialty_name: str,
    symptom_summary: str,
    emergency_detected: bool,
    hospital_name: str,
    in_network: bool,
    coverage_status: str | None,
    estimated_patient_payment: float,
    currency: str | None,
    comparison_reasons: list[str],
) -> str:
    network_message = "esta dentro de tu red" if in_network else "esta fuera de tu red"
    urgency_message = (
        "Detectamos senales de alerta, asi que esta recomendacion debe revisarse con prioridad. "
        if emergency_detected
        else ""
    )
    reasons_message = "; ".join(comparison_reasons[:3])
    return (
        f"{patient_name or 'Paciente'}, te recomiendo atenderte en {hospital_name} porque "
        f"{network_message}, esta alineado con la especialidad de {specialty_name} "
        f"y tu copago estimado seria {_format_money(estimated_patient_payment, currency)}. "
        f"{urgency_message}Resumen: {symptom_summary}. "
        f"Cobertura: {coverage_status or 'no definida'}. "
        f"Motivos clave: {reasons_message}."
    ).strip()


def _format_money(amount: float, currency: str | None) -> str:
    if currency:
        return f"{currency} {amount:.2f}"
    return f"{amount:.2f}"


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())
