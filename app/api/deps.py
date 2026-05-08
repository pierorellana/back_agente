from typing import Annotated

from fastapi import Depends

from app.application.services.care_estimate_service import CareEstimateService
from app.application.services.healthcare_catalog_service import HealthcareCatalogService
from app.application.services.insurance_catalog_service import InsuranceCatalogService
from app.application.services.medical_triage_service import MedicalTriageService
from app.application.services.notion_connection_service import NotionConnectionService
from app.application.services.notion_tables_map_service import NotionTablesMapService
from app.infrastructure.config.settings import Settings, get_settings
from app.infrastructure.services.gemini_client import HttpxGeminiClient
from app.infrastructure.services.notion_client import HttpxNotionClient
from app.infrastructure.services.notion_table_map_store import JsonNotionTableMapStore


def get_notion_client(settings: Annotated[Settings, Depends(get_settings)]) -> HttpxNotionClient:
    return HttpxNotionClient.from_settings(settings)


def get_gemini_client(
    settings: Annotated[Settings, Depends(get_settings)],
) -> HttpxGeminiClient | None:
    if not settings.gemini_api_key:
        return None
    return HttpxGeminiClient.from_settings(settings)


def get_notion_connection_service(
    notion_client: Annotated[HttpxNotionClient, Depends(get_notion_client)],
) -> NotionConnectionService:
    return NotionConnectionService(notion_client=notion_client)


def get_notion_table_map_store(
    settings: Annotated[Settings, Depends(get_settings)],
) -> JsonNotionTableMapStore:
    return JsonNotionTableMapStore(map_path=settings.notion_tables_map_path)


def get_notion_tables_map_service(
    settings: Annotated[Settings, Depends(get_settings)],
    notion_client: Annotated[HttpxNotionClient, Depends(get_notion_client)],
    table_map_store: Annotated[JsonNotionTableMapStore, Depends(get_notion_table_map_store)],
) -> NotionTablesMapService:
    root_page_id = settings.notion_root_page_id or settings.notion_root_page_url
    return NotionTablesMapService(
        notion_client=notion_client,
        table_map_store=table_map_store,
        root_page_id=root_page_id,
        max_depth=settings.notion_discovery_max_depth,
    )


def get_insurance_catalog_service(
    notion_client: Annotated[HttpxNotionClient, Depends(get_notion_client)],
    table_map_store: Annotated[JsonNotionTableMapStore, Depends(get_notion_table_map_store)],
) -> InsuranceCatalogService:
    return InsuranceCatalogService(
        notion_client=notion_client,
        table_map_store=table_map_store,
    )


def get_healthcare_catalog_service(
    notion_client: Annotated[HttpxNotionClient, Depends(get_notion_client)],
    table_map_store: Annotated[JsonNotionTableMapStore, Depends(get_notion_table_map_store)],
) -> HealthcareCatalogService:
    return HealthcareCatalogService(
        notion_client=notion_client,
        table_map_store=table_map_store,
    )


def get_medical_triage_service(
    gemini_client: Annotated[HttpxGeminiClient | None, Depends(get_gemini_client)],
) -> MedicalTriageService:
    return MedicalTriageService(gemini_client=gemini_client)


def get_care_estimate_service(
    catalog_service: Annotated[HealthcareCatalogService, Depends(get_healthcare_catalog_service)],
    triage_service: Annotated[MedicalTriageService, Depends(get_medical_triage_service)],
) -> CareEstimateService:
    return CareEstimateService(
        catalog_service=catalog_service,
        triage_service=triage_service,
    )
