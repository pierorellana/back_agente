import logging
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
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
_GENERAL_MEDICINE_ALIASES = (
    "medicina general",
    "medico general",
    "general medicine",
    "medicina familiar",
    "family medicine",
)
_GEMINI_MIN_SPECIALTY_CONFIDENCE = 0.35
_LABEL_SIMILARITY_THRESHOLD = 0.62
_TEXT_SIMILARITY_THRESHOLD = 0.5
_STOPWORDS = {
    "a",
    "al",
    "atencion",
    "cita",
    "con",
    "consulta",
    "de",
    "del",
    "doctor",
    "doctora",
    "dolor",
    "duele",
    "el",
    "en",
    "es",
    "esta",
    "estoy",
    "la",
    "las",
    "los",
    "malestar",
    "me",
    "medica",
    "medico",
    "mi",
    "mis",
    "molestia",
    "o",
    "paciente",
    "para",
    "por",
    "problema",
    "problemas",
    "que",
    "quiero",
    "se",
    "sintoma",
    "sintomas",
    "soy",
    "tengo",
    "un",
    "una",
    "unas",
    "unos",
    "y",
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

        return _build_fallback_specialty_inference(
            symptom_text=symptom_text,
            specialties=specialties,
            candidate_context=candidate_context,
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
            "Si el texto no corresponde claramente a una especialidad permitida, "
            "elige Medicina General cuando exista en el listado.\n\n"
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
        confidence = _normalize_confidence(payload.get("ai_confidence"))
        if confidence is not None and confidence < _GEMINI_MIN_SPECIALTY_CONFIDENCE:
            raise BusinessRuleError("Gemini returned a low-confidence specialty.")

        specialty, correction_reason = _resolve_specialty_from_gemini_payload(
            payload,
            specialties,
        )

        matched_keywords = payload.get("matched_keywords")
        if not isinstance(matched_keywords, list):
            matched_keywords = []

        specialty_reason = str(
            payload.get("specialty_reason") or "Especialidad seleccionada por Gemini."
        )
        if correction_reason:
            specialty_reason = correction_reason

        return SpecialtyInference(
            specialty_page_id=specialty.page_id,
            specialty_id=str(specialty.properties.get("specialty_id")),
            specialty_name=str(specialty.properties.get("specialty_name")),
            symptom_summary=str(
                payload.get("symptom_summary") or f"Paciente reporta: {symptom_text.strip()}"
            ),
            specialty_reason=specialty_reason,
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

    for item in ordered_candidates:
        item["matched_keywords"] = sorted(set(item["matched_keywords"]))
    return ordered_candidates


def _build_fallback_specialty_inference(
    *,
    symptom_text: str,
    specialties: list[CatalogRecord],
    candidate_context: list[dict[str, Any]],
) -> SpecialtyInference:
    fallback = candidate_context[0] if candidate_context else None
    if fallback is not None:
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

    similar_match = _find_similar_specialty_from_text(symptom_text, specialties)
    if similar_match is not None:
        specialty, matched_keywords = similar_match
        return _build_inference_from_specialty(
            specialty=specialty,
            symptom_text=symptom_text,
            specialty_reason=(
                "Se eligio la especialidad activa mas similar al texto del paciente."
            ),
            matched_keywords=matched_keywords,
        )

    general_specialty = _find_general_medicine_specialty(specialties)
    if general_specialty is None:
        raise BusinessRuleError("Medicina General was not found in the specialty catalog.")

    return _build_inference_from_specialty(
        specialty=general_specialty,
        symptom_text=symptom_text,
        specialty_reason=(
            "No se encontro una especialidad especifica con suficiente similitud; "
            "se derivo a Medicina General."
        ),
        matched_keywords=[],
    )


def _build_inference_from_specialty(
    *,
    specialty: CatalogRecord,
    symptom_text: str,
    specialty_reason: str,
    matched_keywords: list[str],
) -> SpecialtyInference:
    return SpecialtyInference(
        specialty_page_id=specialty.page_id,
        specialty_id=str(specialty.properties.get("specialty_id")),
        specialty_name=str(specialty.properties.get("specialty_name")),
        symptom_summary=f"Paciente reporta: {symptom_text.strip()}",
        specialty_reason=specialty_reason,
        ai_confidence=None,
        matched_keywords=matched_keywords,
    )


def _resolve_specialty_from_gemini_payload(
    payload: dict[str, Any],
    specialties: list[CatalogRecord],
) -> tuple[CatalogRecord, str | None]:
    raw_specialty_id = str(payload.get("specialty_id") or "").strip()
    raw_specialty_name = str(payload.get("specialty_name") or "").strip()

    specialty = _find_exact_specialty_match(
        (raw_specialty_id, raw_specialty_name),
        specialties,
    )
    if specialty is not None:
        return specialty, None

    specialty = _find_similar_specialty_from_labels(
        (raw_specialty_id, raw_specialty_name),
        specialties,
    )
    if specialty is not None:
        return (
            specialty,
            "Gemini no devolvio un specialty_id exacto; se ajusto a la "
            "especialidad activa mas similar del catalogo.",
        )

    raise BusinessRuleError("Gemini returned a specialty that is not similar to the catalog.")


def _find_exact_specialty_match(
    values: tuple[str, ...],
    specialties: list[CatalogRecord],
) -> CatalogRecord | None:
    normalized_values = {_normalize_text(value) for value in values if _normalize_text(value)}
    if not normalized_values:
        return None

    for specialty in specialties:
        specialty_id = _normalize_text(specialty.properties.get("specialty_id"))
        specialty_name = _normalize_text(specialty.properties.get("specialty_name"))
        if specialty_id in normalized_values or specialty_name in normalized_values:
            return specialty

    return None


def _find_similar_specialty_from_labels(
    values: tuple[str, ...],
    specialties: list[CatalogRecord],
) -> CatalogRecord | None:
    best_score = 0.0
    best_specialty: CatalogRecord | None = None

    for raw_value in values:
        query = _normalize_text(raw_value)
        if not query:
            continue

        for specialty in specialties:
            candidate_values = (
                specialty.properties.get("specialty_id"),
                specialty.properties.get("specialty_name"),
                specialty.properties.get("description"),
            )
            for candidate_value in candidate_values:
                candidate = _normalize_text(candidate_value)
                if not candidate:
                    continue

                score = SequenceMatcher(None, query, candidate).ratio()
                if query in candidate or candidate in query:
                    score = max(score, 0.95)

                if score > best_score:
                    best_score = score
                    best_specialty = specialty

    if best_specialty is not None and best_score >= _LABEL_SIMILARITY_THRESHOLD:
        return best_specialty
    return None


def _find_similar_specialty_from_text(
    symptom_text: str,
    specialties: list[CatalogRecord],
) -> tuple[CatalogRecord, list[str]] | None:
    query = _normalize_text(symptom_text)
    query_tokens = _meaningful_tokens(query)
    if not query_tokens:
        return None

    best_score = 0.0
    best_specialty: CatalogRecord | None = None
    best_keywords: list[str] = []

    for specialty in specialties:
        specialty_values = (
            specialty.properties.get("specialty_id"),
            specialty.properties.get("specialty_name"),
            specialty.properties.get("description"),
        )
        candidate = _normalize_text(" ".join(str(value or "") for value in specialty_values))
        candidate_tokens = _meaningful_tokens(candidate)
        if not candidate_tokens:
            continue

        overlap = sorted(query_tokens & candidate_tokens)
        overlap_score = len(overlap) / max(min(len(query_tokens), len(candidate_tokens)), 1)
        label_score = max(
            _similarity_to_catalog_value(query, specialty.properties.get("specialty_id")),
            _similarity_to_catalog_value(query, specialty.properties.get("specialty_name")),
        )
        score = max(overlap_score, label_score)

        if score > best_score:
            best_score = score
            best_specialty = specialty
            best_keywords = overlap

    if best_specialty is not None and best_score >= _TEXT_SIMILARITY_THRESHOLD:
        return best_specialty, best_keywords
    return None


def _find_general_medicine_specialty(specialties: list[CatalogRecord]) -> CatalogRecord | None:
    for specialty in specialties:
        specialty_id = _normalize_text(specialty.properties.get("specialty_id"))
        specialty_name = _normalize_text(specialty.properties.get("specialty_name"))
        for value in (specialty_id, specialty_name):
            if value in _GENERAL_MEDICINE_ALIASES:
                return specialty
            tokens = set(value.split())
            if {"medicina", "general"}.issubset(tokens):
                return specialty
            if {"general", "medicine"}.issubset(tokens):
                return specialty

    return None


def _normalize_confidence(value: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return max(0.0, min(1.0, float(value)))


def _similarity_to_catalog_value(query: str, value: Any) -> float:
    candidate = _normalize_text(value)
    if not candidate:
        return 0.0
    score = SequenceMatcher(None, query, candidate).ratio()
    if candidate in query or query in candidate:
        return max(score, 0.95)
    return score


def _meaningful_tokens(value: str) -> set[str]:
    return {token for token in value.split() if len(token) > 2 and token not in _STOPWORDS}


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
    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_text = "".join(
        character for character in normalized if not unicodedata.combining(character)
    )
    compact = re.sub(r"[^a-z0-9]+", " ", ascii_text.lower())
    return " ".join(compact.split())
