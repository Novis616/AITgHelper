from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.common.time import utc_now
from app.services.incoming_message_responses import (
    cancelled_all_reminders_text,
    cancelled_reminders_by_ids_text,
    category_clarification_text,
    category_notes_not_found_text,
    clarification_text,
    delete_notes_cancelled_text,
    delete_notes_confirmation_text,
    deleted_all_notes_text,
    deleted_notes_by_category_text,
    deleted_notes_by_ids_text,
    deleted_text,
    invalid_delete_confirmation_text,
    list_notes_text,
    list_reminders_text,
    notes_not_found_text,
    not_found_text,
    note_saved_text,
    reminder_cannot_cancel_text,
    reminder_created_text,
    reminder_time_invalid_text,
    reminders_not_found_text,
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
    NoteRead,
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

        active_dialog = await self.dialog_service.get_active_dialog_state(
            telegram_id=message.telegram_id,
        )
        if (
            active_dialog is not None
            and active_dialog.state_type == "confirm_delete_notes"
        ):
            answer = await self._complete_delete_confirmation_dialog(
                message,
                active_dialog,
            )
            return IncomingMessageResult(
                text=answer,
                intent="delete_note",
                parameters=dict(active_dialog.payload),
            )
        if (
            active_dialog is not None
            and active_dialog.state_type == "confirm_delete_reminders"
        ):
            answer = await self._complete_delete_reminders_confirmation_dialog(
                message,
                active_dialog,
            )
            return IncomingMessageResult(
                text=answer,
                intent="delete_reminder",
                parameters=dict(active_dialog.payload),
            )
        if (
            active_dialog is not None
            and active_dialog.state_type == "create_note_category"
        ):
            note = await self._complete_note_category_dialog(message, active_dialog)
            return IncomingMessageResult(
                text=note_saved_text(
                    note,
                    message.language,
                    forwarded=note.source_type == "forwarded",
                ),
                intent="create_note",
                parameters={"category_name": note.category_name},
            )

        if message.is_forwarded:
            return await self._handle_forwarded_text_message(message, text)

        known_categories = await self._known_categories(message.telegram_id)
        intent = await self.ai_service.interpret_message(
            AiInterpretationInput(
                telegram_id=message.telegram_id,
                text=text,
                language=message.language,
                source_type=message.source_type,
                timezone=message.timezone or self.settings.default_timezone,
                known_categories=known_categories,
            )
        )
        answer = await self._apply_intent(message, intent)
        return IncomingMessageResult(
            text=answer,
            intent=intent.intent,
            parameters=dict(intent.parameters),
        )

    async def _handle_forwarded_text_message(
        self,
        message: IncomingTextMessage,
        text: str,
    ) -> IncomingMessageResult:
        intent = IntentResult(intent="unknown")
        try:
            known_categories = await self._known_categories(message.telegram_id)
            intent = await self.ai_service.interpret_message(
                AiInterpretationInput(
                    telegram_id=message.telegram_id,
                    text=text,
                    language=message.language,
                    source_type="forwarded",
                    timezone=message.timezone or self.settings.default_timezone,
                    known_categories=known_categories,
                )
            )
        except Exception:
            intent = IntentResult(intent="unknown")

        parameters = intent.parameters
        if intent.intent == "create_reminder":
            answer = await self._apply_intent(message, intent)
            return IncomingMessageResult(
                text=answer,
                intent=intent.intent,
                parameters=dict(parameters),
            )

        category_name = self._optional_text(parameters, "category_name", "category")
        missing_fields = self._missing_fields(parameters)
        if "category" in missing_fields or (
            self._optional_bool(parameters, "category_required")
            and category_name is None
        ):
            question = await self._ask_for_missing_data(
                message,
                intent,
                ["category"],
                question=(
                    intent.clarification_question
                    or category_clarification_text(message.language)
                ),
                state_type="create_note_category",
                extra_payload={
                    "source_type": "forwarded",
                    "forward": (message.forward or ForwardInfo()).model_dump(),
                },
            )
            return IncomingMessageResult(
                text=question,
                intent="create_note",
                parameters=dict(parameters),
            )

        note = await self.note_service.create_forwarded_text_note(
            CreateForwardedNoteInput(
                telegram_id=message.telegram_id,
                content=text,
                category_name=category_name,
                language=message.language,
                forward=message.forward or ForwardInfo(),
            )
        )
        return IncomingMessageResult(
            text=note_saved_text(note, message.language, forwarded=True),
            intent="create_note",
            parameters=dict(parameters),
        )

    async def _apply_intent(
        self,
        message: IncomingTextMessage,
        intent: IntentResult,
    ) -> str:
        parameters = intent.parameters

        if intent.intent == "create_note":
            content = self._optional_text(parameters, "content", "text", "note")
            category_name = self._optional_text(parameters, "category_name", "category")
            missing_fields = self._missing_fields(parameters)
            if "category" in missing_fields or (
                self._optional_bool(parameters, "category_required")
                and category_name is None
            ):
                return await self._ask_for_missing_data(
                    message,
                    intent,
                    ["category"],
                    question=(
                        intent.clarification_question
                        or category_clarification_text(message.language)
                    ),
                    state_type="create_note_category",
                )
            note = await self.note_service.create_note(
                CreateNoteInput(
                    telegram_id=message.telegram_id,
                    content=content or message.text,
                    title=self._optional_text(parameters, "title"),
                    category_name=category_name,
                    language=message.language,
                )
            )
            return note_saved_text(note, message.language, forwarded=False)

        if intent.intent == "list_notes":
            notes = await self.note_service.list_notes(telegram_id=message.telegram_id)
            return list_notes_text(notes, message.language)

        if intent.intent == "delete_note":
            delete_scope = self._optional_text(parameters, "delete_scope")
            note_ids = self._optional_int_list(parameters, "note_ids", "ids")
            delete_all = self._optional_bool(parameters, "delete_all")
            category_name = self._optional_text(parameters, "category_name", "category")

            if delete_scope == "all" or delete_all:
                return await self._create_delete_confirmation(
                    message,
                    operation_type="delete_all_notes",
                    count=await self.note_service.count_notes(
                        telegram_id=message.telegram_id,
                    ),
                    payload={"delete_all": True},
                    not_found_message=notes_not_found_text(message.language),
                )

            if delete_scope == "category" or (
                category_name is not None and note_ids is None
            ):
                if category_name is None:
                    return await self._ask_for_missing_data(
                        message,
                        intent,
                        ["category"],
                    )
                return await self._create_delete_confirmation(
                    message,
                    operation_type="delete_notes_by_category",
                    count=await self.note_service.count_notes_by_category(
                        telegram_id=message.telegram_id,
                        category_name=category_name,
                    ),
                    payload={"category_name": category_name},
                    not_found_message=category_notes_not_found_text(
                        category_name,
                        message.language,
                    ),
                )

            if note_ids is not None:
                return await self._create_delete_confirmation(
                    message,
                    operation_type="delete_note_ids",
                    count=await self.note_service.count_existing_notes_by_ids(
                        telegram_id=message.telegram_id,
                        note_ids=note_ids,
                    ),
                    payload={"note_ids": note_ids},
                    not_found_message=notes_not_found_text(message.language),
                )

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
            delete_scope = self._optional_text(parameters, "delete_scope")
            reminder_ids = self._optional_int_list(
                parameters,
                "reminder_ids",
                "ids",
            )
            delete_all = self._optional_bool(parameters, "delete_all")

            if delete_scope == "all" or delete_all:
                return await self._create_delete_reminders_confirmation(
                    message,
                    operation_type="delete_all_reminders",
                    count=await self.reminder_service.count_scheduled_reminders(
                        telegram_id=message.telegram_id,
                    ),
                    payload={"delete_all": True},
                    not_found_message=reminders_not_found_text(message.language),
                )

            if delete_scope == "ids" or reminder_ids is not None:
                if reminder_ids is None:
                    return await self._ask_for_missing_data(message, intent, ["id"])
                return await self._create_delete_reminders_confirmation(
                    message,
                    operation_type="delete_reminder_ids",
                    count=await self.reminder_service.count_existing_scheduled_reminders_by_ids(
                        telegram_id=message.telegram_id,
                        reminder_ids=reminder_ids,
                    ),
                    payload={"reminder_ids": reminder_ids},
                    not_found_message=reminders_not_found_text(message.language),
                )

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

    async def _create_delete_confirmation(
        self,
        message: IncomingTextMessage,
        *,
        operation_type: str,
        count: int,
        payload: dict[str, Any],
        not_found_message: str,
    ) -> str:
        if count <= 0:
            return not_found_message
        await self.dialog_service.create_dialog_state(
            CreateDialogStateInput(
                telegram_id=message.telegram_id,
                state_type="confirm_delete_notes",
                payload={
                    "operation_type": operation_type,
                    "count_preview": count,
                    **payload,
                },
                language=message.language,
                timezone=message.timezone or self.settings.default_timezone,
            )
        )
        return delete_notes_confirmation_text(message.language)

    async def _create_delete_reminders_confirmation(
        self,
        message: IncomingTextMessage,
        *,
        operation_type: str,
        count: int,
        payload: dict[str, Any],
        not_found_message: str,
    ) -> str:
        if count <= 0:
            return not_found_message
        await self.dialog_service.create_dialog_state(
            CreateDialogStateInput(
                telegram_id=message.telegram_id,
                state_type="confirm_delete_reminders",
                payload={
                    "operation_type": operation_type,
                    "count_preview": count,
                    **payload,
                },
                language=message.language,
                timezone=message.timezone or self.settings.default_timezone,
            )
        )
        return delete_notes_confirmation_text(message.language)

    async def _complete_delete_confirmation_dialog(
        self,
        message: IncomingTextMessage,
        active_dialog,
    ) -> str:
        answer = self._confirmation_answer(message.text)
        if answer is None:
            return invalid_delete_confirmation_text(message.language)

        if answer is False:
            await self.dialog_service.cancel_dialog_state(
                telegram_id=message.telegram_id,
            )
            return delete_notes_cancelled_text(message.language)

        payload = dict(active_dialog.payload)
        operation_type = str(payload.get("operation_type") or "")
        try:
            if operation_type == "delete_note_ids":
                note_ids = self._coerce_int_list(payload.get("note_ids"))
                deleted_count = await self.note_service.delete_notes_by_ids(
                    telegram_id=message.telegram_id,
                    note_ids=note_ids,
                )
                await self.dialog_service.complete_dialog_state(
                    telegram_id=message.telegram_id,
                )
                return deleted_notes_by_ids_text(deleted_count, message.language)

            if operation_type == "delete_notes_by_category":
                category_name = str(payload.get("category_name") or "").strip()
                deleted_count = await self.note_service.delete_notes_by_category(
                    telegram_id=message.telegram_id,
                    category_name=category_name,
                )
                await self.dialog_service.complete_dialog_state(
                    telegram_id=message.telegram_id,
                )
                return deleted_notes_by_category_text(
                    deleted_count,
                    category_name,
                    message.language,
                )

            if operation_type == "delete_all_notes":
                deleted_count = await self.note_service.delete_all_notes(
                    telegram_id=message.telegram_id,
                )
                await self.dialog_service.complete_dialog_state(
                    telegram_id=message.telegram_id,
                )
                return deleted_all_notes_text(deleted_count, message.language)
        except (NotFoundError, ValidationError):
            await self.dialog_service.complete_dialog_state(
                telegram_id=message.telegram_id,
            )
            if operation_type == "delete_notes_by_category":
                category_name = str(payload.get("category_name") or "").strip()
                return category_notes_not_found_text(category_name, message.language)
            return notes_not_found_text(message.language)

        await self.dialog_service.complete_dialog_state(telegram_id=message.telegram_id)
        return notes_not_found_text(message.language)

    async def _complete_delete_reminders_confirmation_dialog(
        self,
        message: IncomingTextMessage,
        active_dialog,
    ) -> str:
        answer = self._confirmation_answer(message.text)
        if answer is None:
            return invalid_delete_confirmation_text(message.language)

        if answer is False:
            await self.dialog_service.cancel_dialog_state(
                telegram_id=message.telegram_id,
            )
            return delete_notes_cancelled_text(message.language)

        payload = dict(active_dialog.payload)
        operation_type = str(payload.get("operation_type") or "")
        try:
            if operation_type == "delete_reminder_ids":
                reminder_ids = self._coerce_int_list(payload.get("reminder_ids"))
                cancelled_count = await self.reminder_service.cancel_reminders_by_ids(
                    telegram_id=message.telegram_id,
                    reminder_ids=reminder_ids,
                )
                await self.dialog_service.complete_dialog_state(
                    telegram_id=message.telegram_id,
                )
                return cancelled_reminders_by_ids_text(
                    cancelled_count,
                    message.language,
                )

            if operation_type == "delete_all_reminders":
                cancelled_count = (
                    await self.reminder_service.cancel_all_scheduled_reminders(
                        telegram_id=message.telegram_id,
                    )
                )
                await self.dialog_service.complete_dialog_state(
                    telegram_id=message.telegram_id,
                )
                return cancelled_all_reminders_text(
                    cancelled_count,
                    message.language,
                )
        except (NotFoundError, ValidationError):
            await self.dialog_service.complete_dialog_state(
                telegram_id=message.telegram_id,
            )
            return reminders_not_found_text(message.language)

        await self.dialog_service.complete_dialog_state(telegram_id=message.telegram_id)
        return reminders_not_found_text(message.language)

    async def _ask_for_missing_data(
        self,
        message: IncomingTextMessage,
        intent: IntentResult,
        missing_fields: list[str],
        *,
        question: str | None = None,
        state_type: str | None = None,
        extra_payload: dict[str, Any] | None = None,
    ) -> str:
        payload = {
            "original_text": message.text,
            "intent": intent.intent,
            "parameters": dict(intent.parameters),
            "missing_fields": missing_fields,
        }
        if extra_payload:
            payload.update(extra_payload)
        await self.dialog_service.create_dialog_state(
            CreateDialogStateInput(
                telegram_id=message.telegram_id,
                state_type=state_type or intent.intent,
                payload=payload,
                language=message.language,
                timezone=message.timezone or self.settings.default_timezone,
            )
        )
        return clarification_text(
            question or intent.clarification_question,
            message.language,
        )

    async def _complete_note_category_dialog(
        self,
        message: IncomingTextMessage,
        active_dialog,
    ) -> NoteRead:
        payload = dict(active_dialog.payload)
        parameters = payload.get("parameters")
        if not isinstance(parameters, dict):
            parameters = {}
        content = self._optional_text(parameters, "content", "text", "note")
        source_type = str(payload.get("source_type") or "").strip()
        if source_type == "forwarded":
            forward_payload = payload.get("forward")
            if not isinstance(forward_payload, dict):
                forward_payload = {}
            original_text = str(payload.get("original_text") or "").strip()
            note = await self.note_service.create_forwarded_text_note(
                CreateForwardedNoteInput(
                    telegram_id=message.telegram_id,
                    content=original_text,
                    title=self._optional_text(parameters, "title"),
                    category_name=message.text,
                    forward=ForwardInfo.model_validate(forward_payload),
                    language=message.language,
                )
            )
        else:
            note = await self.note_service.create_note(
                CreateNoteInput(
                    telegram_id=message.telegram_id,
                    content=content or str(payload.get("original_text") or "").strip(),
                    title=self._optional_text(parameters, "title"),
                    category_name=message.text,
                    language=message.language,
                )
            )
        await self.dialog_service.complete_dialog_state(
            telegram_id=message.telegram_id,
        )
        return note

    async def _known_categories(self, telegram_id: int) -> list[str]:
        list_category_names = getattr(self.note_service, "list_category_names", None)
        if list_category_names is None:
            return []
        return await list_category_names(telegram_id=telegram_id)

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

    def _optional_int_list(
        self,
        parameters: dict[str, Any],
        *keys: str,
    ) -> list[int] | None:
        for key in keys:
            value = parameters.get(key)
            note_ids = self._coerce_int_list(value)
            if note_ids:
                return note_ids
        return None

    def _coerce_int_list(self, value: Any) -> list[int]:
        if value is None:
            return []
        raw_items = value if isinstance(value, list) else [value]
        ids: list[int] = []
        seen: set[int] = set()
        for item in raw_items:
            try:
                note_id = int(str(item).strip())
            except ValueError:
                continue
            if note_id > 0 and note_id not in seen:
                ids.append(note_id)
                seen.add(note_id)
        return ids

    def _optional_bool(self, parameters: dict[str, Any], *keys: str) -> bool:
        for key in keys:
            value = parameters.get(key)
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.strip().casefold() in {"1", "true", "yes", "да"}
        return False

    def _missing_fields(self, parameters: dict[str, Any]) -> list[str]:
        value = parameters.get("missing_fields")
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    def _confirmation_answer(self, value: str) -> bool | None:
        text = value.strip().casefold()
        if text in {"да", "д", "yes", "y"}:
            return True
        if text in {"нет", "не", "н", "no", "n"}:
            return False
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
