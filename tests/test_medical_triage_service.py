from typing import Any

from app.application.services.healthcare_catalog_service import CatalogRecord
from app.application.services.medical_triage_service import MedicalTriageService


class FakeGeminiClient:
    model = "fake-gemini"

    def __init__(
        self,
        payload: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.payload = payload
        self.error = error

    def generate_json(
        self,
        prompt: str,
        schema: dict[str, Any],
        temperature: float = 0.1,
    ) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        assert self.payload is not None
        return self.payload


def test_invalid_gemini_specialty_is_adjusted_to_similar_catalog_specialty() -> None:
    service = MedicalTriageService(
        gemini_client=FakeGeminiClient(
            payload={
                "symptom_summary": "Dolor posterior a caida.",
                "specialty_id": "orthopedics",
                "specialty_name": "Traumatologia y ortopedia",
                "specialty_reason": "La molestia se relaciona con una lesion.",
                "ai_confidence": 0.82,
                "matched_keywords": [],
            }
        )
    )

    result = service.infer_specialty(
        symptom_text="Me cai y me duele la rodilla.",
        specialties_by_page_id=_specialties_by_page_id(),
        symptom_specialty_maps=[],
    )

    assert result.specialty_id == "traumatologia"
    assert result.specialty_name == "Traumatologia"
    assert "mas similar" in result.specialty_reason


def test_low_confidence_gemini_falls_back_to_general_medicine_without_signal() -> None:
    service = MedicalTriageService(
        gemini_client=FakeGeminiClient(
            payload={
                "symptom_summary": "Solicitud sin sintomas claros.",
                "specialty_id": "neumologia",
                "specialty_name": "Neumologia",
                "specialty_reason": "No hay certeza suficiente.",
                "ai_confidence": 0.1,
                "matched_keywords": [],
            }
        )
    )

    result = service.infer_specialty(
        symptom_text="Solo quiero orientacion administrativa.",
        specialties_by_page_id=_specialties_by_page_id(),
        symptom_specialty_maps=[],
    )

    assert result.specialty_id == "medicina_general"
    assert result.specialty_name == "Medicina General"


def test_without_gemini_or_signal_uses_general_medicine_not_first_catalog_record() -> None:
    service = MedicalTriageService()

    result = service.infer_specialty(
        symptom_text="Solo quiero informacion.",
        specialties_by_page_id=_specialties_by_page_id(),
        symptom_specialty_maps=[],
    )

    assert result.specialty_id == "medicina_general"
    assert result.specialty_name == "Medicina General"


def test_gemini_failure_uses_symptom_keyword_match_before_general_medicine() -> None:
    service = MedicalTriageService(gemini_client=FakeGeminiClient(error=RuntimeError("boom")))

    result = service.infer_specialty(
        symptom_text="Me duele mucho la rodilla despues de una caida.",
        specialties_by_page_id=_specialties_by_page_id(),
        symptom_specialty_maps=[
            CatalogRecord(
                page_id="map_trauma",
                properties={
                    "specialty": ["page_trauma"],
                    "keywords": ["rodilla", "caida"],
                    "ai_weight": 1.0,
                    "confidence_score": 0.5,
                },
            )
        ],
    )

    assert result.specialty_id == "traumatologia"
    assert result.matched_keywords == ["caida", "rodilla"]


def _specialties_by_page_id() -> dict[str, CatalogRecord]:
    records = [
        _specialty(
            page_id="page_neumo",
            specialty_id="neumologia",
            specialty_name="Neumologia",
            description="Pulmones, vias respiratorias, tos y falta de aire.",
        ),
        _specialty(
            page_id="page_general",
            specialty_id="medicina_general",
            specialty_name="Medicina General",
            description="Atencion primaria y orientacion inicial.",
        ),
        _specialty(
            page_id="page_trauma",
            specialty_id="traumatologia",
            specialty_name="Traumatologia",
            description="Lesiones, fracturas, rodilla y huesos.",
        ),
    ]
    return {record.page_id: record for record in records}


def _specialty(
    *,
    page_id: str,
    specialty_id: str,
    specialty_name: str,
    description: str,
) -> CatalogRecord:
    return CatalogRecord(
        page_id=page_id,
        properties={
            "specialty_id": specialty_id,
            "specialty_name": specialty_name,
            "description": description,
        },
    )
