from pathlib import Path

from app.application.dtos.responses.notion_tables_map_response import NotionTablesMapResponse


class JsonNotionTableMapStore:
    def __init__(self, map_path: str) -> None:
        self._map_path = Path(map_path)

    def save(self, table_map: NotionTablesMapResponse) -> None:
        table_map.map_path = self.path
        self._map_path.parent.mkdir(parents=True, exist_ok=True)
        self._map_path.write_text(
            table_map.model_dump_json(indent=2),
            encoding="utf-8",
        )

    def load(self) -> NotionTablesMapResponse:
        return NotionTablesMapResponse.model_validate_json(
            self._map_path.read_text(encoding="utf-8")
        )

    @property
    def path(self) -> str:
        return self._map_path.as_posix()
