from __future__ import annotations

from pydantic import BaseModel, Field

from app.schemas.note import ForwardInfo


class IncomingTextMessage(BaseModel):
    telegram_id: int
    text: str
    language: str = "ru"
    timezone: str | None = None
    source_type: str = "plain"
    forward: ForwardInfo | None = None

    @property
    def is_forwarded(self) -> bool:
        return self.source_type == "forwarded" or self.forward is not None


class IncomingMessageResult(BaseModel):
    text: str
    intent: str = "unknown"
    parameters: dict[str, object] = Field(default_factory=dict)
