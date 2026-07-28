from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

from app.config.settings import Settings
from app.common.errors import ValidationError
from app.schemas import (
    CreateDialogStateInput,
    CreateForwardedNoteInput,
    CreateNoteInput,
    CreateReminderInput,
    IncomingTextMessage,
    IntentResult,
    NoteRead,
    ReminderRead,
)
from app.services import IncomingMessageService


def run(coro):
    return asyncio.run(coro)


class FakeAiService:
    def __init__(self, result: IntentResult) -> None:
        self.result = result
        self.calls = []

    async def interpret_message(self, input_data):
        self.calls.append(input_data)
        return self.result


class FakeNoteService:
    def __init__(self) -> None:
        self.created: list[CreateNoteInput] = []
        self.forwarded: list[CreateForwardedNoteInput] = []
        self.deleted: list[int] = []
        self.listed = [make_note(note_id=11, content="First note")]

    async def create_note(self, data: CreateNoteInput) -> NoteRead:
        self.created.append(data)
        return make_note(note_id=1, content=data.content, language=data.language)

    async def create_forwarded_text_note(
        self,
        data: CreateForwardedNoteInput,
    ) -> NoteRead:
        self.forwarded.append(data)
        return make_note(note_id=2, content=data.content, source_type="forwarded")

    async def list_notes(self, *, telegram_id: int, limit: int = 20) -> list[NoteRead]:
        return self.listed

    async def delete_note(self, *, telegram_id: int, note_id: int) -> None:
        self.deleted.append(note_id)


class FakeReminderService:
    def __init__(self) -> None:
        self.created: list[CreateReminderInput] = []
        self.cancelled: list[int] = []
        self.listed = [make_reminder(reminder_id=21, text="Buy milk")]

    async def create_reminder(self, data: CreateReminderInput) -> ReminderRead:
        self.created.append(data)
        return make_reminder(reminder_id=3, text=data.text, remind_at=data.remind_at)

    async def list_reminders(
        self,
        *,
        telegram_id: int,
        status: str | None = None,
        limit: int = 20,
    ) -> list[ReminderRead]:
        return self.listed

    async def cancel_reminder(
        self,
        *,
        telegram_id: int,
        reminder_id: int,
    ) -> ReminderRead:
        self.cancelled.append(reminder_id)
        return make_reminder(reminder_id=reminder_id, text="Cancelled")


class FailingReminderService(FakeReminderService):
    async def create_reminder(self, data: CreateReminderInput) -> ReminderRead:
        self.created.append(data)
        raise ValidationError("remind_at must be in the future")


class FakeDialogService:
    def __init__(self) -> None:
        self.created: list[CreateDialogStateInput] = []

    async def create_dialog_state(self, data: CreateDialogStateInput):
        self.created.append(data)
        return None


class FakeReminderScheduler:
    def __init__(self) -> None:
        self.scheduled: list[tuple[int, datetime]] = []

    def schedule_reminder(self, reminder_id: int, remind_at_utc: datetime) -> None:
        self.scheduled.append((reminder_id, remind_at_utc))


def make_service(
    intent: IntentResult,
    *,
    note_service: FakeNoteService | None = None,
    reminder_service: FakeReminderService | None = None,
    dialog_service: FakeDialogService | None = None,
    reminder_scheduler: FakeReminderScheduler | None = None,
) -> tuple[IncomingMessageService, FakeAiService, FakeNoteService, FakeReminderService, FakeDialogService]:
    ai_service = FakeAiService(intent)
    notes = note_service or FakeNoteService()
    reminders = reminder_service or FakeReminderService()
    dialogs = dialog_service or FakeDialogService()
    return (
        IncomingMessageService(
            None,  # type: ignore[arg-type]
            ai_service=ai_service,  # type: ignore[arg-type]
            note_service=notes,  # type: ignore[arg-type]
            reminder_service=reminders,  # type: ignore[arg-type]
            dialog_service=dialogs,  # type: ignore[arg-type]
            reminder_scheduler=reminder_scheduler,
            settings=Settings(default_timezone="UTC"),
        ),
        ai_service,
        notes,
        reminders,
        dialogs,
    )


def make_message(text: str = "Save this") -> IncomingTextMessage:
    return IncomingTextMessage(
        telegram_id=42,
        text=text,
        language="en",
        timezone="UTC",
    )


def make_note(
    *,
    note_id: int,
    content: str,
    source_type: str = "plain",
    language: str = "en",
) -> NoteRead:
    now = datetime.now(timezone.utc)
    return NoteRead(
        id=note_id,
        user_id=10,
        title=None,
        content=content,
        source_type=source_type,
        source_chat_id=None,
        source_chat_title=None,
        source_message_id=None,
        forward_sender_name=None,
        language=language,
        created_at=now,
        updated_at=now,
    )


def make_reminder(
    *,
    reminder_id: int,
    text: str,
    remind_at: datetime | None = None,
) -> ReminderRead:
    return ReminderRead(
        id=reminder_id,
        user_id=10,
        text=text,
        remind_at_utc=remind_at or datetime.now(timezone.utc) + timedelta(hours=1),
        timezone="UTC",
        status="scheduled",
        created_at=datetime.now(timezone.utc),
        sent_at=None,
        error_text=None,
    )


def test_incoming_service_maps_create_note() -> None:
    async def scenario() -> None:
        service, ai, notes, _, _ = make_service(
            IntentResult(intent="create_note", parameters={"content": "AI note"})
        )

        result = await service.handle_text_message(make_message("Save this"))

        assert result.intent == "create_note"
        assert result.text == "Done, saved note #1."
        assert ai.calls[0].text == "Save this"
        assert notes.created[0].content == "AI note"

    run(scenario())


def test_incoming_service_keeps_forwarded_text_without_ai_call() -> None:
    async def scenario() -> None:
        service, ai, notes, _, _ = make_service(IntentResult(intent="unknown"))

        result = await service.handle_text_message(
            IncomingTextMessage(
                telegram_id=42,
                text="Forwarded text",
                language="en",
                source_type="forwarded",
            )
        )

        assert result.text == "Done, saved the forwarded message as note #2."
        assert ai.calls == []
        assert notes.forwarded[0].content == "Forwarded text"

    run(scenario())


def test_incoming_service_maps_list_and_delete() -> None:
    async def scenario() -> None:
        list_service, _, _, _, _ = make_service(IntentResult(intent="list_notes"))
        listed = await list_service.handle_text_message(make_message("Show notes"))
        assert listed.text == "Notes:\n#11: First note"

        delete_service, _, notes, _, _ = make_service(
            IntentResult(intent="delete_note", parameters={"id": "11"})
        )
        deleted = await delete_service.handle_text_message(make_message("Delete note 11"))
        assert deleted.text == "Deleted note #11."
        assert notes.deleted == [11]

    run(scenario())


def test_incoming_service_maps_create_reminder_with_iso_datetime() -> None:
    async def scenario() -> None:
        scheduler = FakeReminderScheduler()
        service, _, _, reminders, dialogs = make_service(
            IntentResult(
                intent="create_reminder",
                parameters={
                    "text": "Buy milk",
                    "remind_at": "2026-07-29T09:00:00+00:00",
                },
            ),
            reminder_scheduler=scheduler,
        )

        result = await service.handle_text_message(make_message("Remind me"))

        assert result.intent == "create_reminder"
        assert result.text.startswith("Done, created reminder #3:")
        assert reminders.created[0].text == "Buy milk"
        assert reminders.created[0].remind_at == datetime(
            2026,
            7,
            29,
            9,
            0,
            tzinfo=timezone.utc,
        )
        assert scheduler.scheduled == [(3, reminders.created[0].remind_at)]
        assert dialogs.created == []

    run(scenario())


def test_incoming_service_creates_dialog_for_missing_delete_id() -> None:
    async def scenario() -> None:
        service, _, _, _, dialogs = make_service(
            IntentResult(
                intent="delete_reminder",
                parameters={},
                clarification_question="Which reminder should I cancel?",
            )
        )

        result = await service.handle_text_message(make_message("Cancel reminder"))

        assert result.text == "Which reminder should I cancel?"
        assert dialogs.created[0].state_type == "delete_reminder"
        assert dialogs.created[0].payload["missing_fields"] == ["id"]

    run(scenario())


def test_incoming_service_creates_dialog_for_unreliable_reminder_time() -> None:
    async def scenario() -> None:
        scheduler = FakeReminderScheduler()
        service, _, _, reminders, dialogs = make_service(
            IntentResult(
                intent="create_reminder",
                parameters={"text": "Buy milk", "time": "tomorrow morning"},
            ),
            reminder_scheduler=scheduler,
        )

        result = await service.handle_text_message(make_message("Remind me"))

        assert result.text == "I am not sure what to do. Please write: save a note, show notes, or create a reminder."
        assert reminders.created == []
        assert scheduler.scheduled == []
        assert dialogs.created[0].payload["missing_fields"] == ["remind_at"]

    run(scenario())


def test_incoming_service_does_not_schedule_failed_reminder_creation() -> None:
    async def scenario() -> None:
        scheduler = FakeReminderScheduler()
        reminders = FailingReminderService()
        service, _, _, _, dialogs = make_service(
            IntentResult(
                intent="create_reminder",
                parameters={
                    "text": "Buy milk",
                    "remind_at": "2026-07-29T09:00:00+00:00",
                },
            ),
            reminder_service=reminders,
            reminder_scheduler=scheduler,
        )

        result = await service.handle_text_message(make_message("Remind me"))

        assert result.text == "I need an exact future time. Example: 2026-07-29 09:00."
        assert len(reminders.created) == 1
        assert scheduler.scheduled == []
        assert dialogs.created[0].payload["missing_fields"] == ["remind_at"]

    run(scenario())
