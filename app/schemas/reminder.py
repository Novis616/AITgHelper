from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CreateReminderInput(BaseModel):
    telegram_id: int
    text: str
    remind_at: datetime
    timezone: str | None = None
    language: str = "ru"


class ReminderRead(BaseModel):
    id: int
    user_id: int
    text: str
    remind_at_utc: datetime
    timezone: str
    status: str
    created_at: datetime
    sent_at: datetime | None
    error_text: str | None

    model_config = ConfigDict(from_attributes=True)
