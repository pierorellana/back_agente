from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_insurance_catalog_service
from app.application.dtos.responses.general_response import GeneralResponse
from app.application.services.insurance_catalog_service import InsuranceCatalogService

router = APIRouter(tags=["catalogs"])


@router.get("/insurance-providers", response_model=GeneralResponse[list[dict]])
def list_insurance_providers(
    service: Annotated[InsuranceCatalogService, Depends(get_insurance_catalog_service)],
) -> GeneralResponse[list[dict]]:
    return service.list_providers()


@router.get("/insurance-plans", response_model=GeneralResponse[list[dict]])
def list_insurance_plans(
    service: Annotated[InsuranceCatalogService, Depends(get_insurance_catalog_service)],
) -> GeneralResponse[list[dict]]:
    return service.list_plans()


@router.get("/users", response_model=GeneralResponse[list[dict]])
def list_users(
    service: Annotated[InsuranceCatalogService, Depends(get_insurance_catalog_service)],
) -> GeneralResponse[list[dict]]:
    return service.list_users()


@router.get("/specialties", response_model=GeneralResponse[list[dict]])
def list_specialties(
    service: Annotated[InsuranceCatalogService, Depends(get_insurance_catalog_service)],
) -> GeneralResponse[list[dict]]:
    return service.list_specialties()


@router.get("/hospitals", response_model=GeneralResponse[list[dict]])
def list_hospitals(
    service: Annotated[InsuranceCatalogService, Depends(get_insurance_catalog_service)],
) -> GeneralResponse[list[dict]]:
    return service.list_hospitals()


@router.get("/symptoms", response_model=GeneralResponse[list[dict]])
def list_symptoms(
    service: Annotated[InsuranceCatalogService, Depends(get_insurance_catalog_service)],
) -> GeneralResponse[list[dict]]:
    return service.list_symptoms()


@router.get("/hospital-specialties", response_model=GeneralResponse[list[dict]])
def list_hospital_specialties(
    service: Annotated[InsuranceCatalogService, Depends(get_insurance_catalog_service)],
) -> GeneralResponse[list[dict]]:
    return service.list_hospital_specialties()
