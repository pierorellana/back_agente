from pydantic import BaseModel


class NotionTableMapItem(BaseModel):
    key: str
    title: str
    database_id: str
    data_source_id: str
    data_source_name: str | None = None
    properties: list[str]
    property_types: dict[str, str]


class NotionTablesMapResponse(BaseModel):
    root_page_id: str
    tables_count: int
    tables: list[NotionTableMapItem]
    notion_version: str
    map_path: str | None = None
