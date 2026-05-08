from pydantic import BaseModel


class CareEstimatePatientResponse(BaseModel):
    user_id: str | None = None
    full_name: str | None = None
    member_id: str | None = None
    plan_id: str | None = None
    plan_name: str | None = None


class CareEstimateInterpretationResponse(BaseModel):
    emergency_detected: bool
    severity_level: str | None = None
    matched_emergency_keywords: list[str]
    symptom_summary: str
    specialty_id: str
    specialty_name: str
    specialty_reason: str
    ai_confidence: float | None = None


class HospitalComparisonResponse(BaseModel):
    hospital_id: str
    hospital_name: str
    city: str | None = None
    in_network: bool
    network_status: str | None = None
    coverage_status: str | None = None
    estimated_total_price: float
    estimated_patient_payment: float
    currency: str | None = None
    why_it_matches: list[str]


class CareEstimateRecommendationResponse(BaseModel):
    hospital_id: str
    hospital_name: str
    specialty_id: str
    specialty_name: str
    estimated_patient_payment: float
    currency: str | None = None
    explanation: str


class CareEstimateResponse(BaseModel):
    patient: CareEstimatePatientResponse
    interpretation: CareEstimateInterpretationResponse
    recommendation: CareEstimateRecommendationResponse
    comparisons: list[HospitalComparisonResponse]
    history_saved: bool
