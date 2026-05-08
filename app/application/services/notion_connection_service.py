import logging
from typing import Any

from app.application.dtos.responses.general_response import GeneralResponse
from app.application.dtos.responses.notion_connection_response import NotionConnectionResponse
from app.application.ports.services.notion_client import NotionClientPort
from app.domain.errors import IntegrationError

logger = logging.getLogger("app.notion")


class NotionConnectionService:
    def __init__(self, notion_client: NotionClientPort) -> None:
        self._notion_client = notion_client

    def verify_connection(self) -> GeneralResponse[NotionConnectionResponse]:
        logger.info("notion_connection_check_started")

        database = self._notion_client.retrieve_database()
        data_sources = database.get("data_sources") or []
        data_source_id = self._resolve_data_source_id(data_sources)

        data_source = self._notion_client.retrieve_data_source(data_source_id)
        query = self._notion_client.query_data_source(data_source_id, page_size=3)

        properties = sorted((data_source.get("properties") or {}).keys())
        sample_page_count = len(query.get("results") or [])

        logger.info(
            "notion_connection_check_succeeded database_id=%s data_source_id=%s "
            "properties_count=%s sample_page_count=%s",
            database.get("id"),
            data_source_id,
            len(properties),
            sample_page_count,
        )

        return GeneralResponse(
            success=True,
            message="Notion connection is working",
            data=NotionConnectionResponse(
                connected=True,
                database_id=database.get("id", ""),
                database_title=self._extract_title(database),
                data_source_id=data_source_id,
                data_source_name=data_source.get("name"),
                data_source_count=len(data_sources),
                properties=properties,
                sample_page_count=sample_page_count,
                has_more_pages=bool(query.get("has_more", False)),
                notion_version=self._notion_client.notion_version,
            ),
        )

    def _resolve_data_source_id(self, data_sources: list[dict[str, Any]]) -> str:
        if not data_sources:
            raise IntegrationError(
                "Notion database was found, but it has no data sources available for this token."
            )

        data_source_id = data_sources[0].get("id")
        if not data_source_id:
            raise IntegrationError("Notion database returned a data source without an id.")

        return data_source_id

    def _extract_title(self, database: dict[str, Any]) -> str | None:
        title = database.get("title")
        if not isinstance(title, list):
            return None

        plain_text = "".join(item.get("plain_text", "") for item in title if isinstance(item, dict))
        return plain_text or None
