from functools import lru_cache
import base64
import binascii
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic import model_validator
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
    encryption_enabled: bool = True
    app_encryption_key: str = ""
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

    @model_validator(mode="after")
    def validate_encryption_key(self) -> "Settings":
        if not self.encryption_enabled:
            return self
        if not self.app_encryption_key.strip():
            raise ValueError(
                "APP_ENCRYPTION_KEY is required when encryption is enabled"
            )
        try:
            decoded = base64.urlsafe_b64decode(self.app_encryption_key)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("APP_ENCRYPTION_KEY must be a valid Fernet key") from exc
        if len(decoded) != 32:
            raise ValueError("APP_ENCRYPTION_KEY must decode to 32 bytes")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
