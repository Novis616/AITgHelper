from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CreateDialogStateInput(BaseModel):
    telegram_id: int
    state_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    expires_at: datetime | None = None
    language: str = "ru"
    timezone: str | None = None


class DialogStateRead(BaseModel):
    id: int
    user_id: int
    state_type: str
    status: str
    payload: dict[str, Any]
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
