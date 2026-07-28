from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


AiIntent = Literal[
    "create_note",
    "create_reminder",
    "list_notes",
    "list_reminders",
    "delete_note",
    "delete_reminder",
    "unknown",
]

SUPPORTED_INTENTS: tuple[str, ...] = (
    "create_note",
    "create_reminder",
    "list_notes",
    "list_reminders",
    "delete_note",
    "delete_reminder",
    "unknown",
)


class AiInterpretationInput(BaseModel):
    telegram_id: int
    text: str
    language: str | None = None
    source_type: str = "plain"
    timezone: str | None = None
    dialog_context: dict[str, Any] | None = None


class IntentResult(BaseModel):
    intent: AiIntent = "unknown"
    parameters: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    clarification_question: str | None = None
    raw_response: str | None = None

    @field_validator("intent", mode="before")
    @classmethod
    def normalize_intent(cls, value: object) -> str:
        if not isinstance(value, str):
            return "unknown"
        normalized = value.strip().lower()
        if normalized not in SUPPORTED_INTENTS:
            return "unknown"
        return normalized
