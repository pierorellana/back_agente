from pydantic import BaseModel


class NotionConnectionResponse(BaseModel):
    connected: bool
    database_id: str
    database_title: str | None = None
    data_source_id: str
    data_source_name: str | None = None
    data_source_count: int
    properties: list[str]
    sample_page_count: int
    has_more_pages: bool
    notion_version: str
