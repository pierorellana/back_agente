from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = Field(default="backend-agente-ia", validation_alias="APP_NAME")
    app_version: str = Field(default="0.1.0", validation_alias="APP_VERSION")
    api_prefix: str = Field(default="/api", validation_alias="API_PREFIX")
    debug: bool = Field(default=False, validation_alias="APP_DEBUG")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    cors_allowed_origins: str = Field(default="*", validation_alias="CORS_ALLOWED_ORIGINS")
    cors_allow_credentials: bool = Field(default=False, validation_alias="CORS_ALLOW_CREDENTIALS")

    notion_token: str | None = Field(default=None, validation_alias="NOTION_TOKEN")
    notion_root_page_url: str | None = Field(default=None, validation_alias="NOTION_ROOT_PAGE_URL")
    notion_root_page_id: str | None = Field(default=None, validation_alias="NOTION_ROOT_PAGE_ID")
    notion_database_url: str | None = Field(default=None, validation_alias="NOTION_DATABASE_URL")
    notion_database_id: str | None = Field(default=None, validation_alias="NOTION_DATABASE_ID")
    notion_data_source_id: str | None = Field(
        default=None,
        validation_alias="NOTION_DATA_SOURCE_ID",
    )
    notion_version: str = Field(default="2026-03-11", validation_alias="NOTION_VERSION")
    notion_tables_map_path: str = Field(
        default="config/notion_tables.json",
        validation_alias="NOTION_TABLES_MAP_PATH",
    )
    notion_discovery_max_depth: int = Field(
        default=5,
        validation_alias="NOTION_DISCOVERY_MAX_DEPTH",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
