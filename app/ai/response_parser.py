from __future__ import annotations

import json

from app.schemas.intent_result import IntentResult


def parse_intent_response(raw_response: str) -> IntentResult:
    text = _strip_json_fence(raw_response.strip())
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return IntentResult(
            intent="unknown",
            confidence=0.0,
            clarification_question="Не удалось понять запрос. Можешь переформулировать?",
            raw_response=raw_response,
        )

    if not isinstance(payload, dict):
        return IntentResult(
            intent="unknown",
            confidence=0.0,
            clarification_question="Не удалось понять запрос. Можешь переформулировать?",
            raw_response=raw_response,
        )

    parameters = payload.get("parameters") or {}
    if not isinstance(parameters, dict):
        parameters = {}

    return IntentResult.model_validate(
        {
            "intent": payload.get("intent", "unknown"),
            "parameters": parameters,
            "confidence": payload.get("confidence", 0.0),
            "clarification_question": payload.get("clarification_question"),
            "raw_response": raw_response,
        }
    )


def _strip_json_fence(text: str) -> str:
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return text
