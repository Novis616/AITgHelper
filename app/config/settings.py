from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables or .env."""

    app_env: str = "local"
    log_level: str = "INFO"
    telegram_bot_token: str = ""
    database_url: str = "sqlite+aiosqlite:///./data/aitghelper.sqlite3"
    default_timezone: str = "Europe/Moscow"
    ai_provider: Literal["openai", "openrouter"] = "openai"
    ai_model: str = ""
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    allowed_telegram_user_ids: Annotated[list[int], NoDecode] = Field(
        default_factory=list
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    @field_validator("allowed_telegram_user_ids", mode="before")
    @classmethod
    def parse_allowed_user_ids(cls, value: object) -> list[int]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            return [int(item.strip()) for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
