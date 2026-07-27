from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreateNoteInput(BaseModel):
    telegram_id: int
    content: str
    title: str | None = None
    language: str = "ru"


class ForwardInfo(BaseModel):
    source_chat_id: int | None = None
    source_chat_title: str | None = None
    source_message_id: int | None = None
    forward_sender_name: str | None = None


class CreateForwardedNoteInput(CreateNoteInput):
    forward: ForwardInfo = Field(default_factory=ForwardInfo)


class NoteRead(BaseModel):
    id: int
    user_id: int
    title: str | None
    content: str
    source_type: str
    source_chat_id: int | None
    source_chat_title: str | None
    source_message_id: int | None
    forward_sender_name: str | None
    language: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
