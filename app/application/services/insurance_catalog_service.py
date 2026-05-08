import logging
from typing import Any

from app.application.dtos.responses.general_response import GeneralResponse
from app.application.dtos.responses.notion_tables_map_response import (
    NotionTableMapItem,
    NotionTablesMapResponse,
)
from app.application.ports.services.notion_client import NotionClientPort
from app.application.ports.services.notion_table_map_store import NotionTableMapStorePort
from app.domain.errors import NotFoundError

logger = logging.getLogger("app.catalogs")
_HIDDEN_NOTION_FIELDS = {"created_at"}


class InsuranceCatalogService:
    def __init__(
        self,
        notion_client: NotionClientPort,
        table_map_store: NotionTableMapStorePort,
    ) -> None:
        self._notion_client = notion_client
        self._table_map_store = table_map_store

    def list_providers(self) -> GeneralResponse[list[dict[str, Any]]]:
        return self._list_catalog(
            table_key="insurance_providers",
            success_message="Insurance providers loaded",
        )

    def list_plans(self) -> GeneralResponse[list[dict[str, Any]]]:
        return self._list_catalog(
            table_key="insurance_plans",
            success_message="Insurance plans loaded",
        )

    def list_users(self) -> GeneralResponse[list[dict[str, Any]]]:
        return self._list_catalog(
            table_key="users",
            success_message="Users loaded",
        )

    def list_specialties(self) -> GeneralResponse[list[dict[str, Any]]]:
        return self._list_catalog(
            table_key="specialties",
            success_message="Specialties loaded",
        )

    def list_hospitals(self) -> GeneralResponse[list[dict[str, Any]]]:
        return self._list_catalog(
            table_key="hospitals",
            success_message="Hospitals loaded",
        )

    def list_symptoms(self) -> GeneralResponse[list[dict[str, Any]]]:
        return self._list_catalog(
            table_key="symptoms",
            success_message="Symptoms loaded",
        )

    def list_hospital_specialties(self) -> GeneralResponse[list[dict[str, Any]]]:
        return self._list_catalog(
            table_key="hospital_specialties",
            success_message="Hospital specialties loaded",
        )

    def list_symptom_specialty_map(self) -> GeneralResponse[list[dict[str, Any]]]:
        return self._list_catalog(
            table_key="symptom_specialty_map",
            success_message="Symptom specialty map loaded",
        )

    def list_insurance_network(self) -> GeneralResponse[list[dict[str, Any]]]:
        return self._list_catalog(
            table_key="insurance_network",
            success_message="Insurance network loaded",
        )

    def list_emergency_keywords(self) -> GeneralResponse[list[dict[str, Any]]]:
        return self._list_catalog(
            table_key="emergency_keywords",
            success_message="Emergency keywords loaded",
        )

    def _list_catalog(
        self,
        table_key: str,
        success_message: str,
    ) -> GeneralResponse[list[dict[str, Any]]]:
        table_map = self._load_table_map()
        table = self._find_table(table_map, table_key)

        logger.info(
            "catalog_list_started table_key=%s data_source_id=%s",
            table.key,
            table.data_source_id,
        )

        pages = self._notion_client.query_data_source_pages(table.data_source_id)
        items = [_notion_page_to_record(page) for page in pages]

        logger.info("catalog_list_succeeded table_key=%s count=%s", table.key, len(items))
        return GeneralResponse(
            success=True,
            message=success_message,
            data=items,
        )

    def _load_table_map(self) -> NotionTablesMapResponse:
        try:
            return self._table_map_store.load()
        except FileNotFoundError as exc:
            raise NotFoundError(
                "Notion tables map does not exist yet. Run POST /api/notion/tables/sync first."
            ) from exc

    def _find_table(
        self,
        table_map: NotionTablesMapResponse,
        table_key: str,
    ) -> NotionTableMapItem:
        for table in table_map.tables:
            if table.key == table_key:
                return table

        raise NotFoundError(f"Notion table '{table_key}' was not found in the local table map.")


def _notion_page_to_record(page: dict[str, Any]) -> dict[str, Any]:
    record: dict[str, Any] = {}

    properties = page.get("properties") or {}
    for property_name, property_payload in properties.items():
        if property_name in _HIDDEN_NOTION_FIELDS:
            continue

        if isinstance(property_payload, dict):
            record[property_name] = _extract_property_value(property_payload)

    return record


def _extract_property_value(property_payload: dict[str, Any]) -> Any:
    property_type = property_payload.get("type")

    if property_type in {"title", "rich_text"}:
        return _plain_text(property_payload.get(property_type) or [])
    if property_type == "number":
        return property_payload.get("number")
    if property_type in {"checkbox", "url", "email", "phone_number", "created_time"}:
        return property_payload.get(property_type)
    if property_type in {"select", "status"}:
        selected = property_payload.get(property_type)
        return selected.get("name") if isinstance(selected, dict) else None
    if property_type == "multi_select":
        return [
            item.get("name")
            for item in property_payload.get("multi_select") or []
            if isinstance(item, dict)
        ]
    if property_type == "date":
        value = property_payload.get("date")
        if not isinstance(value, dict):
            return None
        return {
            "start": value.get("start"),
            "end": value.get("end"),
            "time_zone": value.get("time_zone"),
        }
    if property_type == "relation":
        return [
            relation.get("id")
            for relation in property_payload.get("relation") or []
            if isinstance(relation, dict)
        ]
    if property_type == "formula":
        formula = property_payload.get("formula") or {}
        return formula.get(formula.get("type")) if isinstance(formula, dict) else None
    if property_type == "rollup":
        rollup = property_payload.get("rollup") or {}
        return rollup.get(rollup.get("type")) if isinstance(rollup, dict) else None
    if property_type == "people":
        return [
            person.get("name") or person.get("id")
            for person in property_payload.get("people") or []
            if isinstance(person, dict)
        ]
    if property_type == "files":
        return [
            file_payload.get("name")
            for file_payload in property_payload.get("files") or []
            if isinstance(file_payload, dict)
        ]

    return property_payload.get(property_type)


def _plain_text(rich_text_items: list[dict[str, Any]]) -> str:
    return "".join(
        item.get("plain_text", "")
        for item in rich_text_items
        if isinstance(item, dict)
    )
