from typing import Any

from fastapi.testclient import TestClient

from app.application.dtos.responses.care_estimate_response import (
    CareEstimateInterpretationResponse,
    CareEstimatePatientResponse,
    CareEstimateRecommendationResponse,
    CareEstimateResponse,
    HospitalComparisonResponse,
)
from app.application.dtos.responses.general_response import GeneralResponse
from app.main import app


class FakeCareEstimateService:
    def estimate_care(self, request: Any) -> GeneralResponse[CareEstimateResponse]:
        return GeneralResponse(
            success=True,
            message="Care estimate calculated",
            data=CareEstimateResponse(
                patient=CareEstimatePatientResponse(
                    user_id="0922334455",
                    full_name="Paciente Demo",
                    member_id="MEM-001",
                    plan_id="plan_premium",
                    plan_name="Premium Plus",
                ),
                interpretation=CareEstimateInterpretationResponse(
                    emergency_detected=False,
                    severity_level=None,
                    matched_emergency_keywords=[],
                    symptom_summary="Dolor toracico intermitente sin perdida de conciencia.",
                    specialty_id="cardiology",
                    specialty_name="Cardiology",
                    specialty_reason="Gemini sugirio esta especialidad por el tipo de sintoma.",
                    ai_confidence=0.88,
                ),
                recommendation=CareEstimateRecommendationResponse(
                    hospital_id="hosp_santa_ana",
                    hospital_name="Clinica Santa Ana",
                    specialty_id="cardiology",
                    specialty_name="Cardiology",
                    estimated_patient_payment=25.0,
                    currency="USD",
                    explanation=(
                        "Te recomiendo atenderte en Clinica Santa Ana porque esta dentro de tu "
                        "red y tiene el copago mas bajo."
                    ),
                ),
                comparisons=[
                    HospitalComparisonResponse(
                        hospital_id="hosp_santa_ana",
                        hospital_name="Clinica Santa Ana",
                        city="Guayaquil",
                        in_network=True,
                        network_status="In network",
                        coverage_status="Covered",
                        estimated_total_price=80.0,
                        estimated_patient_payment=25.0,
                        currency="USD",
                        why_it_matches=[
                            "Esta dentro de la red del plan.",
                            "La especialidad evaluada es Cardiology.",
                            "Estado de cobertura: Covered.",
                            "Copago estimado: USD 25.00.",
                        ],
                    )
                ],
                history_saved=True,
            ),
        )


def test_care_estimate_endpoint() -> None:
    from app.api.deps import get_care_estimate_service

    def override_service() -> Any:
        return FakeCareEstimateService()

    app.dependency_overrides[get_care_estimate_service] = override_service
    client = TestClient(app)

    response = client.post(
        "/api/care-estimates",
        json={
            "document_number": "0922334455",
            "symptom_text": "Tengo dolor en el pecho y me cuesta respirar al caminar.",
        },
    )

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["patient"]["user_id"] == "0922334455"
    assert body["data"]["recommendation"]["hospital_id"] == "hosp_santa_ana"
    assert len(body["data"]["comparisons"]) == 1
