from __future__ import annotations

import json

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
- Use unknown when intent is unclear.
- confidence must be a number from 0 to 1.
- parameters must be an object.
- clarification_question must be null unless required data is missing.
- For reminders, include text and remind_at when available.
- Support Russian and English messages.
"""


def build_user_prompt(input_data: AiInterpretationInput) -> str:
    payload = {
        "message": input_data.text,
        "language_hint": input_data.language,
        "source_type": input_data.source_type,
        "timezone": input_data.timezone,
        "dialog_context": input_data.dialog_context,
        "allowed_intents": SUPPORTED_INTENTS,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
