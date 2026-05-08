import logging
from dataclasses import dataclass
from typing import Any

from app.application.dtos.requests.care_estimate_request import CareEstimateRequest
from app.application.dtos.responses.care_estimate_response import (
    CareEstimateInterpretationResponse,
    CareEstimatePatientResponse,
    CareEstimateRecommendationResponse,
    CareEstimateResponse,
    HospitalComparisonResponse,
)
from app.application.dtos.responses.general_response import GeneralResponse
from app.application.services.healthcare_catalog_service import (
    CatalogRecord,
    EstimationCatalogContext,
    HealthcareCatalogService,
)
from app.application.services.medical_triage_service import (
    EmergencyMatch,
    MedicalTriageService,
    SpecialtyInference,
)
from app.domain.errors import BusinessRuleError

logger = logging.getLogger("app.care_estimate")

_MAX_HOSPITAL_OPTIONS = 3


@dataclass(frozen=True)
class RankedHospitalOption:
    hospital: CatalogRecord
    in_network: bool
    network_status: str | None
    coverage_status: str | None
    estimated_total_price: float
    estimated_patient_payment: float
    currency: str | None
    why_it_matches: list[str]


class CareEstimateService:
    def __init__(
        self,
        catalog_service: HealthcareCatalogService,
        triage_service: MedicalTriageService,
    ) -> None:
        self._catalog_service = catalog_service
        self._triage_service = triage_service

    def estimate_care(self, request: CareEstimateRequest) -> GeneralResponse[CareEstimateResponse]:
        logger.info("care_estimate_started document_number=%s", request.document_number)
        context = self._catalog_service.load_estimation_context()
        patient = self._catalog_service.find_patient(context, request.document_number)
        plan = self._catalog_service.resolve_patient_plan(context, patient)

        emergency_match = self._triage_service.evaluate_emergency(
            request.symptom_text,
            context.emergency_keywords,
        )
        specialty_inference = self._resolve_specialty(
            context=context,
            symptom_text=request.symptom_text,
            emergency_match=emergency_match,
        )
        specialty = context.specialties_by_page_id.get(specialty_inference.specialty_page_id)
        if specialty is None:
            raise BusinessRuleError("The selected specialty could not be resolved in the catalog.")

        ranked_options = self._rank_hospitals(
            context=context,
            plan=plan,
            specialty=specialty,
        )
        if not ranked_options:
            raise BusinessRuleError(
                "No hospitals with active prices were found for the selected specialty."
            )

        top_options = ranked_options[:_MAX_HOSPITAL_OPTIONS]
        recommended_option = top_options[0]
        explanation = self._triage_service.generate_recommendation_explanation(
            patient_name=_as_optional_text(patient.properties.get("full_name")),
            specialty_name=specialty_inference.specialty_name,
            symptom_summary=specialty_inference.symptom_summary,
            emergency_detected=emergency_match.detected,
            hospital_name=str(recommended_option.hospital.properties.get("hospital_name") or ""),
            in_network=recommended_option.in_network,
            coverage_status=recommended_option.coverage_status,
            estimated_patient_payment=recommended_option.estimated_patient_payment,
            currency=recommended_option.currency,
            comparison_reasons=recommended_option.why_it_matches,
        )
        history_saved = self._catalog_service.save_estimation_history(
            context,
            patient=patient,
            specialty=specialty,
            hospital=recommended_option.hospital,
            input_text=request.symptom_text,
            estimated_patient_payment=recommended_option.estimated_patient_payment,
            emergency_detected=emergency_match.detected,
        )

        response = CareEstimateResponse(
            patient=CareEstimatePatientResponse(
                user_id=_as_optional_text(patient.properties.get("user_id")),
                full_name=_as_optional_text(patient.properties.get("full_name")),
                member_id=_as_optional_text(patient.properties.get("member_id")),
                plan_id=_as_optional_text(plan.properties.get("plan_id")),
                plan_name=_as_optional_text(plan.properties.get("plan_name")),
            ),
            interpretation=CareEstimateInterpretationResponse(
                emergency_detected=emergency_match.detected,
                severity_level=emergency_match.severity_level,
                matched_emergency_keywords=emergency_match.matched_keywords,
                symptom_summary=specialty_inference.symptom_summary,
                specialty_id=specialty_inference.specialty_id,
                specialty_name=specialty_inference.specialty_name,
                specialty_reason=specialty_inference.specialty_reason,
                ai_confidence=specialty_inference.ai_confidence,
            ),
            recommendation=CareEstimateRecommendationResponse(
                hospital_id=str(recommended_option.hospital.properties.get("hospital_id") or ""),
                hospital_name=str(
                    recommended_option.hospital.properties.get("hospital_name") or ""
                ),
                specialty_id=specialty_inference.specialty_id,
                specialty_name=specialty_inference.specialty_name,
                estimated_patient_payment=recommended_option.estimated_patient_payment,
                currency=recommended_option.currency,
                explanation=explanation,
            ),
            comparisons=[
                HospitalComparisonResponse(
                    hospital_id=str(option.hospital.properties.get("hospital_id") or ""),
                    hospital_name=str(option.hospital.properties.get("hospital_name") or ""),
                    city=_as_optional_text(option.hospital.properties.get("city")),
                    in_network=option.in_network,
                    network_status=option.network_status,
                    coverage_status=option.coverage_status,
                    estimated_total_price=option.estimated_total_price,
                    estimated_patient_payment=option.estimated_patient_payment,
                    currency=option.currency,
                    why_it_matches=option.why_it_matches,
                )
                for option in top_options
            ],
            history_saved=history_saved,
        )
        logger.info(
            "care_estimate_succeeded patient=%s specialty=%s recommendation=%s",
            patient.properties.get("user_id"),
            specialty_inference.specialty_id,
            recommended_option.hospital.properties.get("hospital_id"),
        )
        return GeneralResponse(
            success=True,
            message="Care estimate calculated",
            data=response,
        )

    def _resolve_specialty(
        self,
        *,
        context: EstimationCatalogContext,
        symptom_text: str,
        emergency_match: EmergencyMatch,
    ) -> SpecialtyInference:
        if emergency_match.detected and emergency_match.specialty_page_id:
            specialty = context.specialties_by_page_id.get(emergency_match.specialty_page_id)
            if specialty is not None:
                return SpecialtyInference(
                    specialty_page_id=specialty.page_id,
                    specialty_id=str(specialty.properties.get("specialty_id")),
                    specialty_name=str(specialty.properties.get("specialty_name")),
                    symptom_summary=f"Paciente reporta: {symptom_text.strip()}",
                    specialty_reason=(
                        "Se priorizo esta especialidad por una coincidencia con EMERGENCY_KEYWORDS."
                    ),
                    ai_confidence=1.0,
                    matched_keywords=emergency_match.matched_keywords,
                )

        return self._triage_service.infer_specialty(
            symptom_text=symptom_text,
            specialties_by_page_id=context.specialties_by_page_id,
            symptom_specialty_maps=context.symptom_specialty_maps,
        )

    def _rank_hospitals(
        self,
        *,
        context: EstimationCatalogContext,
        plan: CatalogRecord,
        specialty: CatalogRecord,
    ) -> list[RankedHospitalOption]:
        specialty_page_id = specialty.page_id
        price_records = [
            record
            for record in context.consultation_prices
            if specialty_page_id in _relation_ids(record.properties.get("specialty"))
        ]

        if not price_records:
            return []

        coverage_record = self._resolve_coverage(context, plan.page_id, specialty_page_id)
        network_by_hospital_id = self._build_network_lookup(context, plan.page_id)
        options: list[RankedHospitalOption] = []

        for price_record in price_records:
            hospital_page_id = _first_relation_id(price_record.properties.get("hospital"))
            if not hospital_page_id:
                continue

            hospital = context.hospitals_by_page_id.get(hospital_page_id)
            if hospital is None:
                continue

            base_price = price_record.properties.get("base_price")
            if not isinstance(base_price, (int, float)):
                continue

            network_record = network_by_hospital_id.get(hospital_page_id)
            in_network, network_status = _resolve_network_status(network_record)
            coverage_status = _resolve_coverage_status(coverage_record)
            patient_payment = _calculate_patient_payment(
                base_price=float(base_price),
                in_network=in_network,
                plan=plan.properties,
                coverage=coverage_record.properties if coverage_record else None,
                network=network_record.properties if network_record else None,
            )
            currency = _as_optional_text(
                price_record.properties.get("currency") or plan.properties.get("currency")
            )
            why_it_matches = _build_match_reasons(
                in_network=in_network,
                coverage_status=coverage_status,
                estimated_patient_payment=patient_payment,
                currency=currency,
                specialty_name=_as_optional_text(specialty.properties.get("specialty_name")) or "",
            )
            options.append(
                RankedHospitalOption(
                    hospital=hospital,
                    in_network=in_network,
                    network_status=network_status,
                    coverage_status=coverage_status,
                    estimated_total_price=round(float(base_price), 2),
                    estimated_patient_payment=round(patient_payment, 2),
                    currency=currency,
                    why_it_matches=why_it_matches,
                )
            )

        options.sort(
            key=lambda option: (
                0 if option.in_network else 1,
                0 if _coverage_is_positive(option.coverage_status) else 1,
                option.estimated_patient_payment,
                option.estimated_total_price,
                str(option.hospital.properties.get("hospital_name") or ""),
            )
        )
        return options

    def _resolve_coverage(
        self,
        context: EstimationCatalogContext,
        plan_page_id: str,
        specialty_page_id: str,
    ) -> CatalogRecord | None:
        candidates = [
            record
            for record in context.coverages
            if plan_page_id in _relation_ids(record.properties.get("plan"))
            and specialty_page_id in _relation_ids(record.properties.get("specialty"))
        ]
        if not candidates:
            return None

        candidates.sort(
            key=lambda record: (
                0 if _coverage_is_positive(_resolve_coverage_status(record)) else 1,
                str(record.properties.get("coverage_id") or ""),
            )
        )
        return candidates[0]

    def _build_network_lookup(
        self,
        context: EstimationCatalogContext,
        plan_page_id: str,
    ) -> dict[str, CatalogRecord]:
        lookup: dict[str, CatalogRecord] = {}
        for record in context.insurance_networks:
            if plan_page_id not in _relation_ids(record.properties.get("plan")):
                continue

            hospital_page_id = _first_relation_id(record.properties.get("hospital"))
            if not hospital_page_id or hospital_page_id in lookup:
                continue
            lookup[hospital_page_id] = record

        return lookup


def _calculate_patient_payment(
    *,
    base_price: float,
    in_network: bool,
    plan: dict[str, Any],
    coverage: dict[str, Any] | None,
    network: dict[str, Any] | None,
) -> float:
    fixed_copay = coverage.get("in_network_copay_amount") if coverage else None
    if in_network and isinstance(fixed_copay, (int, float)):
        return round(float(fixed_copay), 2)

    if in_network:
        percentage = _normalize_percentage(
            (coverage or {}).get("in_network_patient_percentage")
            or plan.get("default_coinsurance_in_network_pct")
        )
        if percentage is None:
            return round(base_price, 2)
        return round(base_price * percentage / 100, 2)

    percentage = _normalize_percentage(
        (coverage or {}).get("out_network_patient_percentage")
        or plan.get("default_coinsurance_out_network_pct")
    )
    multiplier = network.get("out_of_network_penalty_multiplier") if network else None
    factor = float(multiplier) if isinstance(multiplier, (int, float)) else 1.0

    if percentage is None:
        return round(base_price * factor, 2)

    return round(base_price * percentage / 100 * factor, 2)


def _resolve_network_status(network_record: CatalogRecord | None) -> tuple[bool, str | None]:
    if network_record is None:
        return False, "Out of network"

    raw_status = _as_optional_text(network_record.properties.get("network_status"))
    normalized_status = _normalize_text(raw_status)
    if "out" in normalized_status:
        return False, raw_status or "Out of network"
    if "in" in normalized_status or "active" in normalized_status:
        return True, raw_status or "In network"
    return True, raw_status


def _resolve_coverage_status(coverage_record: CatalogRecord | None) -> str | None:
    if coverage_record is None:
        return "Not configured"

    raw_status = _as_optional_text(coverage_record.properties.get("coverage_status"))
    return raw_status or "Configured"


def _coverage_is_positive(status: str | None) -> bool:
    normalized = _normalize_text(status)
    if not normalized or normalized in {"configured"}:
        return True
    return not any(word in normalized for word in ("deny", "excluded", "inactive", "not covered"))


def _build_match_reasons(
    *,
    in_network: bool,
    coverage_status: str | None,
    estimated_patient_payment: float,
    currency: str | None,
    specialty_name: str,
) -> list[str]:
    reasons = [
        "Esta dentro de la red del plan." if in_network else "No esta dentro de la red del plan.",
        f"La especialidad evaluada es {specialty_name}.",
        f"Estado de cobertura: {coverage_status or 'no definido'}.",
        f"Copago estimado: {_format_money(estimated_patient_payment, currency)}.",
    ]
    return reasons


def _relation_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _first_relation_id(value: Any) -> str | None:
    if not isinstance(value, list) or not value:
        return None
    first = value[0]
    return str(first) if first else None


def _normalize_percentage(value: Any) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    percentage = float(value)
    if 0 < percentage <= 1:
        return percentage * 100
    return percentage


def _format_money(amount: float, currency: str | None) -> str:
    if currency:
        return f"{currency} {amount:.2f}"
    return f"{amount:.2f}"


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _as_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
