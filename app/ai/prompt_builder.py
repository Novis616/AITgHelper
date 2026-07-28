from __future__ import annotations

import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.schemas.intent_result import AiInterpretationInput, SUPPORTED_INTENTS


SYSTEM_PROMPT = """You interpret Telegram messages for AITgHelper.
Return only valid JSON with these fields:
intent, parameters, confidence, clarification_question.

Supported intents:
create_note, create_reminder, list_notes, list_reminders,
delete_note, delete_reminder, unknown.

Rules:
- Use create_note when the user wants to save information.
- Use create_reminder when the user asks to be reminded.
- Use list_notes or list_reminders when the user asks to show saved items.
- Use delete_note or delete_reminder when the user asks to remove an item.
- Use delete_note for deleting one note, several notes, all notes in a note
  category, or all notes.
- Use unknown when intent is unclear.
- confidence must be a number from 0 to 1.
- parameters must be an object.
- clarification_question must be null unless required data is missing.
- For reminders, include text and remind_at when available.
- Resolve relative reminder times using current_datetime_utc and timezone.
- For remind_at, always return ISO 8601 datetime, never phrases like "tomorrow" or "in 2 minutes".
- For notes, include content when available.
- For deleting notes, include structured parameters:
  delete_scope: "ids" | "category" | "all".
- For deleting specific notes, include note_ids as an array of integers, for
  example {"delete_scope": "ids", "note_ids": [1, 3, 7]}.
- For deleting notes in a category, include category_name and
  delete_scope: "category". Do not set delete_all for category deletion.
- For deleting every note, include delete_scope: "all" and delete_all: true.
- For deleting a single note, you may return id or note_id as before.
- For notes, include category_name when the user explicitly names a category,
  for example "сохрани в закладку покупки", "добавь в категорию покупки",
  or "save to shopping".
- If known_categories contains a confident match for a similar note, reuse the
  existing category name exactly as listed there.
- For source_type "forwarded", still treat the message as a note and use these
  same note category rules. Do not create a separate forwarded category system.
- If a note should have a category but you are not sure which one, set
  parameters.missing_fields to ["category"] and ask for the category in
  clarification_question.
- Support Russian and English messages.
"""


def build_user_prompt(input_data: AiInterpretationInput) -> str:
    current_utc = datetime.now(timezone.utc)
    payload = {
        "message": input_data.text,
        "language_hint": input_data.language,
        "source_type": input_data.source_type,
        "timezone": input_data.timezone,
        "current_datetime_utc": current_utc.isoformat(),
        "current_datetime_local": _local_datetime_iso(current_utc, input_data.timezone),
        "dialog_context": input_data.dialog_context,
        "known_categories": input_data.known_categories,
        "allowed_intents": SUPPORTED_INTENTS,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)


def _local_datetime_iso(current_utc: datetime, timezone_name: str | None) -> str:
    if not timezone_name:
        return current_utc.isoformat()
    try:
        return current_utc.astimezone(ZoneInfo(timezone_name)).isoformat()
    except ZoneInfoNotFoundError:
        return current_utc.isoformat()
