from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utc_now
from app.services.incoming_message_responses import (
    clarification_text,
    deleted_text,
    list_notes_text,
    list_reminders_text,
    not_found_text,
    note_saved_text,
    reminder_cannot_cancel_text,
    reminder_created_text,
    reminder_time_invalid_text,
)
from app.common.errors import NotFoundError, ValidationError
from app.config.settings import Settings, get_settings
from app.schemas import (
    AiInterpretationInput,
    CreateDialogStateInput,
    CreateForwardedNoteInput,
    CreateNoteInput,
    CreateReminderInput,
    ForwardInfo,
    IncomingMessageResult,
    IncomingTextMessage,
    IntentResult,
)
from app.services.ai_interpretation_service import AiInterpretationService
from app.services.dialog_service import DialogService
from app.services.note_service import NoteService
from app.services.reminder_service import ReminderService


class ReminderSchedulingPort(Protocol):
    def schedule_reminder(self, reminder_id: int, remind_at_utc: datetime) -> None:
        """Schedule a newly created reminder in the current process."""


class IncomingMessageService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        ai_service: AiInterpretationService | None = None,
        note_service: NoteService | None = None,
        reminder_service: ReminderService | None = None,
        dialog_service: DialogService | None = None,
        reminder_scheduler: ReminderSchedulingPort | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.ai_service = ai_service or AiInterpretationService(
            session,
            settings=self.settings,
        )
        self.note_service = note_service or NoteService(session)
        self.reminder_service = reminder_service or ReminderService(
            session,
            settings=self.settings,
        )
        self.dialog_service = dialog_service or DialogService(
            session,
            settings=self.settings,
        )
        self.reminder_scheduler = reminder_scheduler

    async def handle_text_message(
        self,
        message: IncomingTextMessage,
    ) -> IncomingMessageResult:
        text = message.text.strip()
        if not text:
            raise ValidationError("text must not be empty")

        if message.is_forwarded:
            note = await self.note_service.create_forwarded_text_note(
                CreateForwardedNoteInput(
                    telegram_id=message.telegram_id,
                    content=text,
                    language=message.language,
                    forward=message.forward or ForwardInfo(),
                )
            )
            return IncomingMessageResult(
                text=note_saved_text(note, message.language, forwarded=True),
                intent="create_note",
            )

        intent = await self.ai_service.interpret_message(
            AiInterpretationInput(
                telegram_id=message.telegram_id,
                text=text,
                language=message.language,
                source_type=message.source_type,
                timezone=message.timezone or self.settings.default_timezone,
            )
        )
        answer = await self._apply_intent(message, intent)
        return IncomingMessageResult(
            text=answer,
            intent=intent.intent,
            parameters=dict(intent.parameters),
        )

    async def _apply_intent(
        self,
        message: IncomingTextMessage,
        intent: IntentResult,
    ) -> str:
        parameters = intent.parameters

        if intent.intent == "create_note":
            content = self._optional_text(parameters, "content", "text", "note")
            note = await self.note_service.create_note(
                CreateNoteInput(
                    telegram_id=message.telegram_id,
                    content=content or message.text,
                    title=self._optional_text(parameters, "title"),
                    language=message.language,
                )
            )
            return note_saved_text(note, message.language, forwarded=False)

        if intent.intent == "list_notes":
            notes = await self.note_service.list_notes(telegram_id=message.telegram_id)
            return list_notes_text(notes, message.language)

        if intent.intent == "delete_note":
            note_id = self._optional_int(parameters, "id", "note_id")
            if note_id is None:
                return await self._ask_for_missing_data(message, intent, ["id"])
            try:
                await self.note_service.delete_note(
                    telegram_id=message.telegram_id,
                    note_id=note_id,
                )
            except NotFoundError:
                return not_found_text("note", message.language)
            return deleted_text("note", note_id, message.language)

        if intent.intent == "create_reminder":
            reminder_text = self._optional_text(
                parameters,
                "text",
                "content",
                "reminder_text",
            )
            remind_at = self._optional_datetime(
                parameters,
                "remind_at",
                "datetime",
                "date_time",
                "time",
            )
            missing_fields = []
            if reminder_text is None:
                missing_fields.append("text")
            if remind_at is None:
                missing_fields.append("remind_at")
            if missing_fields:
                return await self._ask_for_missing_data(message, intent, missing_fields)
            try:
                reminder = await self.reminder_service.create_reminder(
                    CreateReminderInput(
                        telegram_id=message.telegram_id,
                        text=reminder_text,
                        remind_at=remind_at,
                        timezone=self._optional_text(parameters, "timezone")
                        or message.timezone
                        or self.settings.default_timezone,
                        language=message.language,
                    )
                )
            except ValidationError:
                return await self._ask_for_missing_data(
                    message,
                    intent,
                    ["remind_at"],
                    question=reminder_time_invalid_text(message.language),
                )
            if self.reminder_scheduler is not None:
                self.reminder_scheduler.schedule_reminder(
                    reminder.id,
                    reminder.remind_at_utc,
                )
            return reminder_created_text(reminder, message.language)

        if intent.intent == "list_reminders":
            reminders = await self.reminder_service.list_reminders(
                telegram_id=message.telegram_id,
                status="scheduled",
            )
            return list_reminders_text(reminders, message.language)

        if intent.intent == "delete_reminder":
            reminder_id = self._optional_int(parameters, "id", "reminder_id")
            if reminder_id is None:
                return await self._ask_for_missing_data(message, intent, ["id"])
            try:
                await self.reminder_service.cancel_reminder(
                    telegram_id=message.telegram_id,
                    reminder_id=reminder_id,
                )
            except NotFoundError:
                return not_found_text("reminder", message.language)
            except ValidationError:
                return reminder_cannot_cancel_text(message.language)
            return deleted_text("reminder", reminder_id, message.language)

        return await self._ask_for_missing_data(message, intent, [])

    async def _ask_for_missing_data(
        self,
        message: IncomingTextMessage,
        intent: IntentResult,
        missing_fields: list[str],
        *,
        question: str | None = None,
    ) -> str:
        await self.dialog_service.create_dialog_state(
            CreateDialogStateInput(
                telegram_id=message.telegram_id,
                state_type=intent.intent,
                payload={
                    "original_text": message.text,
                    "intent": intent.intent,
                    "parameters": dict(intent.parameters),
                    "missing_fields": missing_fields,
                },
                language=message.language,
                timezone=message.timezone or self.settings.default_timezone,
            )
        )
        return clarification_text(
            question or intent.clarification_question,
            message.language,
        )

    def _optional_text(self, parameters: dict[str, Any], *keys: str) -> str | None:
        for key in keys:
            value = parameters.get(key)
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return None

    def _optional_int(self, parameters: dict[str, Any], *keys: str) -> int | None:
        for key in keys:
            value = parameters.get(key)
            if value is None:
                continue
            try:
                return int(str(value).strip())
            except ValueError:
                continue
        return None

    def _optional_datetime(
        self,
        parameters: dict[str, Any],
        *keys: str,
    ) -> datetime | None:
        for key in keys:
            value = parameters.get(key)
            if isinstance(value, datetime):
                return value
            if not isinstance(value, str):
                continue
            text = value.strip()
            if not text:
                continue
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                relative = self._relative_datetime(text)
                if relative is not None:
                    return relative
        return None

    def _relative_datetime(self, value: str) -> datetime | None:
        text = value.strip().lower()
        match = re.fullmatch(
            r"(?:in|\u0447\u0435\u0440\u0435\u0437)\s+(\d+)\s+"
            r"(minute|minutes|min|"
            r"\u043c\u0438\u043d\u0443\u0442\u0430|"
            r"\u043c\u0438\u043d\u0443\u0442\u0443|"
            r"\u043c\u0438\u043d\u0443\u0442\u044b|"
            r"\u043c\u0438\u043d\u0443\u0442|"
            r"hour|hours|"
            r"\u0447\u0430\u0441|"
            r"\u0447\u0430\u0441\u0430|"
            r"\u0447\u0430\u0441\u043e\u0432|"
            r"day|days|"
            r"\u0434\u0435\u043d\u044c|"
            r"\u0434\u043d\u044f|"
            r"\u0434\u043d\u0435\u0439)",
            text,
        )
        if match is None:
            return None

        amount = int(match.group(1))
        unit = match.group(2)
        seconds_by_unit = {
            "minute": 60,
            "minutes": 60,
            "min": 60,
            "\u043c\u0438\u043d\u0443\u0442\u0430": 60,
            "\u043c\u0438\u043d\u0443\u0442\u0443": 60,
            "\u043c\u0438\u043d\u0443\u0442\u044b": 60,
            "\u043c\u0438\u043d\u0443\u0442": 60,
            "hour": 3600,
            "hours": 3600,
            "\u0447\u0430\u0441": 3600,
            "\u0447\u0430\u0441\u0430": 3600,
            "\u0447\u0430\u0441\u043e\u0432": 3600,
            "day": 86400,
            "days": 86400,
            "\u0434\u0435\u043d\u044c": 86400,
            "\u0434\u043d\u044f": 86400,
            "\u0434\u043d\u0435\u0439": 86400,
        }
        return utc_now() + timedelta(seconds=amount * seconds_by_unit[unit])
