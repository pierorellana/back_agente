import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.application.dtos.responses.notion_tables_map_response import (
    NotionTableMapItem,
    NotionTablesMapResponse,
)
from app.application.ports.services.notion_client import NotionClientPort
from app.application.ports.services.notion_table_map_store import NotionTableMapStorePort
from app.domain.errors import NotFoundError

logger = logging.getLogger("app.healthcare_catalog")

_REQUIRED_TABLE_KEYS = (
    "users",
    "insurance_plans",
    "specialties",
    "hospitals",
    "symptom_specialty_map",
    "coverages",
    "insurance_network",
    "consultation_prices",
    "emergency_keywords",
)


@dataclass(frozen=True)
class CatalogRecord:
    page_id: str
    properties: dict[str, Any]


@dataclass(frozen=True)
class EstimationCatalogContext:
    users: list[CatalogRecord]
    plans_by_page_id: dict[str, CatalogRecord]
    specialties_by_page_id: dict[str, CatalogRecord]
    specialties_by_business_id: dict[str, CatalogRecord]
    hospitals_by_page_id: dict[str, CatalogRecord]
    symptom_specialty_maps: list[CatalogRecord]
    coverages: list[CatalogRecord]
    insurance_networks: list[CatalogRecord]
    consultation_prices: list[CatalogRecord]
    emergency_keywords: list[CatalogRecord]
    estimation_history_table: NotionTableMapItem | None


class HealthcareCatalogService:
    def __init__(
        self,
        notion_client: NotionClientPort,
        table_map_store: NotionTableMapStorePort,
    ) -> None:
        self._notion_client = notion_client
        self._table_map_store = table_map_store

    def load_estimation_context(self) -> EstimationCatalogContext:
        table_map = self._load_table_map()
        tables_by_key = {table.key: table for table in table_map.tables}

        missing_tables = [
            table_key for table_key in _REQUIRED_TABLE_KEYS if table_key not in tables_by_key
        ]
        if missing_tables:
            missing = ", ".join(sorted(missing_tables))
            raise NotFoundError(
                f"Notion tables map is missing required tables for estimation: {missing}."
            )

        logger.info("healthcare_catalog_context_loading_started")

        users = self._load_table_rows(tables_by_key["users"])
        plans = self._load_table_rows(tables_by_key["insurance_plans"])
        specialties = self._load_table_rows(tables_by_key["specialties"])
        hospitals = self._load_table_rows(tables_by_key["hospitals"])
        symptom_specialty_maps = self._load_table_rows(tables_by_key["symptom_specialty_map"])
        coverages = self._load_table_rows(tables_by_key["coverages"])
        insurance_networks = self._load_table_rows(tables_by_key["insurance_network"])
        consultation_prices = self._load_table_rows(tables_by_key["consultation_prices"])
        emergency_keywords = self._load_table_rows(tables_by_key["emergency_keywords"])

        context = EstimationCatalogContext(
            users=[record for record in users if _is_record_active(record.properties)],
            plans_by_page_id={
                record.page_id: record
                for record in plans
                if _is_record_active(record.properties)
            },
            specialties_by_page_id={
                record.page_id: record
                for record in specialties
                if _is_record_active(record.properties)
            },
            specialties_by_business_id={
                str(record.properties.get("specialty_id")): record
                for record in specialties
                if _is_record_active(record.properties) and record.properties.get("specialty_id")
            },
            hospitals_by_page_id={
                record.page_id: record
                for record in hospitals
                if _is_record_active(record.properties)
            },
            symptom_specialty_maps=[
                record
                for record in symptom_specialty_maps
                if _is_record_active(record.properties)
            ],
            coverages=[
                record for record in coverages if _is_record_active(record.properties)
            ],
            insurance_networks=[
                record for record in insurance_networks if _is_record_active(record.properties)
            ],
            consultation_prices=[
                record for record in consultation_prices if _is_record_active(record.properties)
            ],
            emergency_keywords=[
                record for record in emergency_keywords if _is_record_active(record.properties)
            ],
            estimation_history_table=tables_by_key.get("estimation_history"),
        )

        logger.info(
            (
                "healthcare_catalog_context_loading_succeeded "
                "users=%s plans=%s specialties=%s hospitals=%s"
            ),
            len(context.users),
            len(context.plans_by_page_id),
            len(context.specialties_by_page_id),
            len(context.hospitals_by_page_id),
        )
        return context

    def find_patient(
        self,
        context: EstimationCatalogContext,
        document_number: str,
    ) -> CatalogRecord:
        normalized_document = _normalize_text(document_number)

        for record in context.users:
            candidates = (
                record.properties.get("user_id"),
                record.properties.get("member_id"),
                record.properties.get("email"),
            )
            if any(_normalize_text(candidate) == normalized_document for candidate in candidates):
                return record

        raise NotFoundError(
            (
                "Patient was not found. For this MVP the document_number is matched "
                "against user_id or member_id."
            )
        )

    def resolve_patient_plan(
        self,
        context: EstimationCatalogContext,
        patient: CatalogRecord,
    ) -> CatalogRecord:
        related_plan_ids = _relation_ids(patient.properties.get("insurance_plan"))
        if not related_plan_ids:
            raise NotFoundError("The patient does not have an insurance plan linked in Notion.")

        for page_id in related_plan_ids:
            plan = context.plans_by_page_id.get(page_id)
            if plan is not None:
                return plan

        raise NotFoundError("The patient's insurance plan could not be resolved from Notion.")

    def save_estimation_history(
        self,
        context: EstimationCatalogContext,
        *,
        patient: CatalogRecord,
        specialty: CatalogRecord,
        hospital: CatalogRecord,
        input_text: str,
        estimated_patient_payment: float,
        emergency_detected: bool,
    ) -> bool:
        history_table = context.estimation_history_table
        if history_table is None:
            logger.warning("healthcare_catalog_history_table_missing")
            return False

        properties = _build_estimation_history_properties(
            history_table=history_table,
            patient=patient,
            specialty=specialty,
            hospital=hospital,
            input_text=input_text,
            estimated_patient_payment=estimated_patient_payment,
            emergency_detected=emergency_detected,
        )
        if not properties:
            logger.warning("healthcare_catalog_history_properties_empty")
            return False

        self._notion_client.create_page(
            parent_data_source_id=history_table.data_source_id,
            properties=properties,
        )
        logger.info("healthcare_catalog_history_saved")
        return True

    def _load_table_map(self) -> NotionTablesMapResponse:
        try:
            return self._table_map_store.load()
        except FileNotFoundError as exc:
            raise NotFoundError(
                "Notion tables map does not exist yet. Run POST /api/notion/tables/sync first."
            ) from exc

    def _load_table_rows(self, table: NotionTableMapItem) -> list[CatalogRecord]:
        pages = self._notion_client.query_data_source_pages(table.data_source_id)
        return [_notion_page_to_catalog_record(page) for page in pages]


def _build_estimation_history_properties(
    *,
    history_table: NotionTableMapItem,
    patient: CatalogRecord,
    specialty: CatalogRecord,
    hospital: CatalogRecord,
    input_text: str,
    estimated_patient_payment: float,
    emergency_detected: bool,
) -> dict[str, Any]:
    property_types = history_table.property_types
    properties: dict[str, Any] = {}
    timestamp = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    estimation_id = f"est_{uuid4().hex[:12]}"

    if property_types.get("estimation_id") == "title":
        properties["estimation_id"] = {
            "title": [{"type": "text", "text": {"content": estimation_id}}]
        }
    if property_types.get("user") == "relation":
        properties["user"] = {"relation": [{"id": patient.page_id}]}
    if property_types.get("input_text") == "rich_text":
        properties["input_text"] = {
            "rich_text": [{"type": "text", "text": {"content": _truncate_notion_text(input_text)}}]
        }
    if property_types.get("chosen_hospital") == "relation":
        properties["chosen_hospital"] = {"relation": [{"id": hospital.page_id}]}
    if property_types.get("chosen_specialty") == "relation":
        properties["chosen_specialty"] = {"relation": [{"id": specialty.page_id}]}
    if property_types.get("estimated_patient_payment") == "number":
        properties["estimated_patient_payment"] = {"number": round(estimated_patient_payment, 2)}
    if property_types.get("emergency_detected") == "checkbox":
        properties["emergency_detected"] = {"checkbox": emergency_detected}
    if property_types.get("created_at") == "date":
        properties["created_at"] = {"date": {"start": timestamp}}

    return properties


def _notion_page_to_catalog_record(page: dict[str, Any]) -> CatalogRecord:
    record: dict[str, Any] = {}

    properties = page.get("properties") or {}
    for property_name, property_payload in properties.items():
        if isinstance(property_payload, dict):
            record[property_name] = _extract_property_value(property_payload)

    return CatalogRecord(
        page_id=str(page.get("id", "")),
        properties=record,
    )


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


def _relation_ids(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item]


def _is_record_active(properties: dict[str, Any]) -> bool:
    active = properties.get("active")
    return active is not False


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().lower().split())


def _truncate_notion_text(value: str, limit: int = 1900) -> str:
    compact = " ".join(value.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."
