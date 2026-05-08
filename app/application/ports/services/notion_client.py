from typing import Any, Protocol


class NotionClientPort(Protocol):
    notion_version: str

    def retrieve_database(self) -> dict[str, Any]:
        pass

    def retrieve_database_by_id(self, database_id: str) -> dict[str, Any]:
        pass

    def retrieve_data_source(self, data_source_id: str) -> dict[str, Any]:
        pass

    def query_data_source(self, data_source_id: str, page_size: int = 3) -> dict[str, Any]:
        pass

    def query_data_source_pages(
        self,
        data_source_id: str,
        page_size: int = 100,
    ) -> list[dict[str, Any]]:
        pass

    def discover_child_databases(
        self,
        root_block_id: str,
        max_depth: int = 5,
    ) -> list[dict[str, str]]:
        pass
