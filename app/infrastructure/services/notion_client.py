import logging
import re
from typing import Any

import httpx

from app.domain.errors import IntegrationError
from app.infrastructure.config.settings import Settings

logger = logging.getLogger("app.notion")

_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_COMPACT_UUID_RE = re.compile(r"[0-9a-fA-F]{32}")


class HttpxNotionClient:
    def __init__(
        self,
        token: str,
        database_id: str,
        notion_version: str,
        timeout_seconds: float = 15.0,
    ) -> None:
        self._database_id = normalize_notion_id(database_id)
        self.notion_version = notion_version
        self._client = httpx.Client(
            base_url="https://api.notion.com/v1",
            timeout=timeout_seconds,
            headers={
                "Authorization": f"Bearer {token}",
                "Notion-Version": notion_version,
                "Content-Type": "application/json",
            },
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "HttpxNotionClient":
        token = settings.notion_token
        database_id = settings.notion_database_id or settings.notion_database_url

        if not token:
            raise IntegrationError("NOTION_TOKEN is not configured.")
        if not database_id:
            raise IntegrationError("NOTION_DATABASE_ID or NOTION_DATABASE_URL is not configured.")

        return cls(
            token=token,
            database_id=database_id,
            notion_version=settings.notion_version,
        )

    def retrieve_database(self) -> dict[str, Any]:
        logger.info(
            "notion_retrieve_database_started database_id=%s notion_version=%s",
            self._database_id,
            self.notion_version,
        )
        response = self._send("GET", f"/databases/{self._database_id}", "retrieve_database")

        if _is_page_instead_of_database_error(response):
            logger.warning(
                "notion_configured_id_is_page page_id=%s scanning_child_blocks=true",
                self._database_id,
            )
            child_database_id = self._find_first_child_database_id(self._database_id)
            if not child_database_id:
                raise IntegrationError(
                    "The Notion URL points to a page, not a database, and no child database "
                    "was found inside that page."
                )

            logger.info(
                "notion_child_database_found page_id=%s database_id=%s",
                self._database_id,
                child_database_id,
            )
            self._database_id = child_database_id
            response = self._send("GET", f"/databases/{self._database_id}", "retrieve_database")

        return self._handle_response(response, "retrieve_database")

    def retrieve_database_by_id(self, database_id: str) -> dict[str, Any]:
        normalized_database_id = normalize_notion_id(database_id)
        logger.info("notion_retrieve_database_by_id_started database_id=%s", normalized_database_id)
        response = self._send("GET", f"/databases/{normalized_database_id}", "retrieve_database")
        return self._handle_response(response, "retrieve_database")

    def retrieve_data_source(self, data_source_id: str) -> dict[str, Any]:
        logger.info("notion_retrieve_data_source_started data_source_id=%s", data_source_id)
        response = self._send("GET", f"/data_sources/{data_source_id}", "retrieve_data_source")
        return self._handle_response(response, "retrieve_data_source")

    def query_data_source(self, data_source_id: str, page_size: int = 3) -> dict[str, Any]:
        logger.info(
            "notion_query_data_source_started data_source_id=%s page_size=%s",
            data_source_id,
            page_size,
        )
        response = self._send(
            "POST",
            f"/data_sources/{data_source_id}/query",
            "query_data_source",
            json={"page_size": page_size},
        )
        return self._handle_response(response, "query_data_source")

    def query_data_source_pages(
        self,
        data_source_id: str,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        logger.info(
            "notion_query_data_source_pages_started data_source_id=%s page_size=%s",
            data_source_id,
            page_size,
        )

        results: list[dict[str, Any]] = []
        start_cursor: str | None = None

        while True:
            body: dict[str, Any] = {"page_size": page_size}
            if start_cursor:
                body["start_cursor"] = start_cursor

            response = self._send(
                "POST",
                f"/data_sources/{data_source_id}/query",
                "query_data_source_pages",
                json=body,
            )
            payload = self._handle_response(response, "query_data_source_pages")
            results.extend(payload.get("results") or [])

            if not payload.get("has_more"):
                logger.info(
                    "notion_query_data_source_pages_succeeded data_source_id=%s count=%s",
                    data_source_id,
                    len(results),
                )
                return results

            start_cursor = payload.get("next_cursor")
            if not start_cursor:
                logger.warning(
                    "notion_query_data_source_pages_missing_cursor data_source_id=%s count=%s",
                    data_source_id,
                    len(results),
                )
                return results

    def discover_child_databases(
        self,
        root_block_id: str,
        max_depth: int = 5,
    ) -> list[dict[str, str]]:
        normalized_root_block_id = normalize_notion_id(root_block_id)
        logger.info(
            "notion_discover_child_databases_started root_block_id=%s max_depth=%s",
            normalized_root_block_id,
            max_depth,
        )

        discovered: dict[str, dict[str, str]] = {}
        visited_blocks: set[str] = set()
        self._collect_child_databases(
            block_id=normalized_root_block_id,
            remaining_depth=max_depth,
            discovered=discovered,
            visited_blocks=visited_blocks,
        )

        logger.info("notion_discover_child_databases_succeeded count=%s", len(discovered))
        return list(discovered.values())

    def _find_first_child_database_id(self, block_id: str, max_depth: int = 3) -> str | None:
        if max_depth < 0:
            return None

        response = self._send(
            "GET",
            f"/blocks/{block_id}/children",
            "retrieve_block_children",
            params={"page_size": 100},
        )
        payload = self._handle_response(response, "retrieve_block_children")

        for block in payload.get("results") or []:
            if block.get("type") == "child_database":
                return normalize_notion_id(block.get("id", ""))

        for block in payload.get("results") or []:
            if block.get("has_children"):
                child_id = block.get("id")
                if not child_id:
                    continue
                found_id = self._find_first_child_database_id(child_id, max_depth=max_depth - 1)
                if found_id:
                    return found_id

        return None

    def _collect_child_databases(
        self,
        block_id: str,
        remaining_depth: int,
        discovered: dict[str, dict[str, str]],
        visited_blocks: set[str],
    ) -> None:
        if remaining_depth < 0 or block_id in visited_blocks:
            return

        visited_blocks.add(block_id)
        children = self._list_block_children(block_id)

        for block in children:
            block_id_value = block.get("id")
            block_type = block.get("type")
            if not block_id_value or not block_type:
                continue

            if block_type == "child_database":
                database_id = normalize_notion_id(block_id_value)
                discovered[database_id] = {
                    "database_id": database_id,
                    "title": str((block.get("child_database") or {}).get("title") or ""),
                }
                logger.info(
                    "notion_child_database_discovered database_id=%s title=%s",
                    database_id,
                    discovered[database_id]["title"],
                )
                continue

            if block.get("has_children"):
                self._collect_child_databases(
                    block_id=normalize_notion_id(block_id_value),
                    remaining_depth=remaining_depth - 1,
                    discovered=discovered,
                    visited_blocks=visited_blocks,
                )

    def _list_block_children(self, block_id: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        start_cursor: str | None = None

        while True:
            params: dict[str, Any] = {"page_size": 100}
            if start_cursor:
                params["start_cursor"] = start_cursor

            response = self._send(
                "GET",
                f"/blocks/{block_id}/children",
                "retrieve_block_children",
                params=params,
            )
            payload = self._handle_response(response, "retrieve_block_children")
            results.extend(payload.get("results") or [])

            if not payload.get("has_more"):
                return results

            start_cursor = payload.get("next_cursor")
            if not start_cursor:
                return results

    def _send(self, method: str, url: str, operation: str, **kwargs: Any) -> httpx.Response:
        try:
            return self._client.request(method, url, **kwargs)
        except httpx.HTTPError as exc:
            logger.exception("notion_%s_transport_failed error=%s", operation, exc)
            raise IntegrationError(
                f"Could not reach Notion while running {operation}: {exc}"
            ) from exc

    def _handle_response(self, response: httpx.Response, operation: str) -> dict[str, Any]:
        if response.is_success:
            logger.info("notion_%s_succeeded status_code=%s", operation, response.status_code)
            return response.json()

        error_code = "unknown_error"
        error_message = response.text
        try:
            payload = response.json()
            error_code = payload.get("code", error_code)
            error_message = payload.get("message", error_message)
        except ValueError:
            pass

        logger.error(
            "notion_%s_failed status_code=%s code=%s message=%s",
            operation,
            response.status_code,
            error_code,
            error_message,
        )
        raise IntegrationError(
            f"Notion {operation} failed with status {response.status_code}: {error_message}"
        )


def normalize_notion_id(raw_value: str) -> str:
    uuid_match = _UUID_RE.search(raw_value)
    if uuid_match:
        return uuid_match.group(0).lower()

    compact_match = _COMPACT_UUID_RE.search(raw_value)
    if not compact_match:
        raise IntegrationError("Could not extract a valid Notion id.")

    compact = compact_match.group(0).lower()
    return (
        f"{compact[0:8]}-{compact[8:12]}-{compact[12:16]}-"
        f"{compact[16:20]}-{compact[20:32]}"
    )


def _is_page_instead_of_database_error(response: httpx.Response) -> bool:
    if response.status_code != 400:
        return False

    try:
        payload = response.json()
    except ValueError:
        return False

    message = str(payload.get("message", "")).lower()
    return "is a page, not a database" in message
