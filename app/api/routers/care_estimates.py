from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_care_estimate_service
from app.application.dtos.requests.care_estimate_request import CareEstimateRequest
from app.application.dtos.responses.care_estimate_response import CareEstimateResponse
from app.application.dtos.responses.general_response import GeneralResponse
from app.application.services.care_estimate_service import CareEstimateService

router = APIRouter(prefix="/care-estimates", tags=["care-estimates"])


@router.post("", response_model=GeneralResponse[CareEstimateResponse])
def estimate_care(
    request: CareEstimateRequest,
    service: Annotated[CareEstimateService, Depends(get_care_estimate_service)],
) -> GeneralResponse[CareEstimateResponse]:
    return service.estimate_care(request)
