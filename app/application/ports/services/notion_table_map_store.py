from typing import Protocol

from app.application.dtos.responses.notion_tables_map_response import NotionTablesMapResponse


class NotionTableMapStorePort(Protocol):
    def save(self, table_map: NotionTablesMapResponse) -> None:
        pass

    def load(self) -> NotionTablesMapResponse:
        pass
