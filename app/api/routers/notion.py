from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_notion_connection_service, get_notion_tables_map_service
from app.application.dtos.responses.general_response import GeneralResponse
from app.application.dtos.responses.notion_connection_response import NotionConnectionResponse
from app.application.dtos.responses.notion_tables_map_response import NotionTablesMapResponse
from app.application.services.notion_connection_service import NotionConnectionService
from app.application.services.notion_tables_map_service import NotionTablesMapService

router = APIRouter(prefix="/notion", tags=["notion"])


@router.get("/connection", response_model=GeneralResponse[NotionConnectionResponse])
def verify_notion_connection(
    service: Annotated[NotionConnectionService, Depends(get_notion_connection_service)],
) -> GeneralResponse[NotionConnectionResponse]:
    return service.verify_connection()


@router.get("/tables/discover", response_model=GeneralResponse[NotionTablesMapResponse])
def discover_notion_tables(
    service: Annotated[NotionTablesMapService, Depends(get_notion_tables_map_service)],
) -> GeneralResponse[NotionTablesMapResponse]:
    return service.discover()


@router.post("/tables/sync", response_model=GeneralResponse[NotionTablesMapResponse])
def sync_notion_tables_map(
    service: Annotated[NotionTablesMapService, Depends(get_notion_tables_map_service)],
) -> GeneralResponse[NotionTablesMapResponse]:
    return service.sync()


@router.get("/tables/map", response_model=GeneralResponse[NotionTablesMapResponse])
def get_notion_tables_map(
    service: Annotated[NotionTablesMapService, Depends(get_notion_tables_map_service)],
) -> GeneralResponse[NotionTablesMapResponse]:
    return service.load()
