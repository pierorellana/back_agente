import logging
import re
from typing import Any

from app.application.dtos.responses.general_response import GeneralResponse
from app.application.dtos.responses.notion_tables_map_response import (
    NotionTableMapItem,
    NotionTablesMapResponse,
)
from app.application.ports.services.notion_client import NotionClientPort
from app.application.ports.services.notion_table_map_store import NotionTableMapStorePort
from app.domain.errors import IntegrationError, NotFoundError

logger = logging.getLogger("app.notion")


class NotionTablesMapService:
    def __init__(
        self,
        notion_client: NotionClientPort,
        table_map_store: NotionTableMapStorePort,
        root_page_id: str | None,
        max_depth: int,
    ) -> None:
        self._notion_client = notion_client
        self._table_map_store = table_map_store
        self._root_page_id = root_page_id
        self._max_depth = max_depth

    def discover(self) -> GeneralResponse[NotionTablesMapResponse]:
        table_map = self._build_map()
        return GeneralResponse(
            success=True,
            message="Notion tables discovered",
            data=table_map,
        )

    def sync(self) -> GeneralResponse[NotionTablesMapResponse]:
        table_map = self._build_map()
        self._table_map_store.save(table_map)
        logger.info(
            "notion_tables_map_synced tables_count=%s map_path=%s",
            table_map.tables_count,
            table_map.map_path,
        )
        return GeneralResponse(
            success=True,
            message="Notion tables map synchronized",
            data=table_map,
        )

    def load(self) -> GeneralResponse[NotionTablesMapResponse]:
        try:
            table_map = self._table_map_store.load()
        except FileNotFoundError as exc:
            raise NotFoundError(
                "Notion tables map does not exist yet. Run POST /api/notion/tables/sync first."
            ) from exc

        return GeneralResponse(
            success=True,
            message="Notion tables map loaded",
            data=table_map,
        )

    def _build_map(self) -> NotionTablesMapResponse:
        root_page_id = self._resolve_root_page_id()
        logger.info(
            "notion_tables_discovery_started root_page_id=%s max_depth=%s",
            root_page_id,
            self._max_depth,
        )

        child_databases = self._notion_client.discover_child_databases(
            root_block_id=root_page_id,
            max_depth=self._max_depth,
        )
        tables: list[NotionTableMapItem] = []
        used_keys: set[str] = set()

        for child_database in child_databases:
            database_id = child_database["database_id"]
            database = self._notion_client.retrieve_database_by_id(database_id)
            data_source = self._resolve_first_data_source(database)
            data_source_id = data_source["id"]
            data_source_details = self._notion_client.retrieve_data_source(data_source_id)
            properties = data_source_details.get("properties") or {}
            title = self._extract_title(database) or child_database["title"] or database_id
            key = self._build_unique_key(title, used_keys)

            tables.append(
                NotionTableMapItem(
                    key=key,
                    title=title,
                    database_id=database_id,
                    data_source_id=data_source_id,
                    data_source_name=data_source.get("name"),
                    properties=sorted(properties.keys()),
                    property_types=self._extract_property_types(properties),
                )
            )

        logger.info("notion_tables_discovery_succeeded tables_count=%s", len(tables))
        return NotionTablesMapResponse(
            root_page_id=root_page_id,
            tables_count=len(tables),
            tables=tables,
            notion_version=self._notion_client.notion_version,
        )

    def _resolve_root_page_id(self) -> str:
        if not self._root_page_id:
            raise IntegrationError("NOTION_ROOT_PAGE_ID or NOTION_ROOT_PAGE_URL is not configured.")
        return self._root_page_id

    def _resolve_first_data_source(self, database: dict[str, Any]) -> dict[str, Any]:
        data_sources = database.get("data_sources") or []
        if not data_sources:
            raise IntegrationError(f"Database {database.get('id')} has no data sources.")

        data_source = data_sources[0]
        if not data_source.get("id"):
            raise IntegrationError(
                f"Database {database.get('id')} returned a data source without id."
            )

        return data_source

    def _extract_title(self, database: dict[str, Any]) -> str | None:
        title = database.get("title")
        if not isinstance(title, list):
            return None

        plain_text = "".join(item.get("plain_text", "") for item in title if isinstance(item, dict))
        return plain_text or None

    def _build_unique_key(self, title: str, used_keys: set[str]) -> str:
        base_key = _slugify(title)
        key = base_key
        counter = 2

        while key in used_keys:
            key = f"{base_key}_{counter}"
            counter += 1

        used_keys.add(key)
        return key

    def _extract_property_types(self, properties: dict[str, Any]) -> dict[str, str]:
        return {
            property_name: str(property_payload.get("type", "unknown"))
            for property_name, property_payload in properties.items()
            if isinstance(property_payload, dict)
        }


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", value.strip().lower()).strip("_")
    return slug or "notion_table"
