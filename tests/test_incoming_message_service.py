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
    ForwardInfo,
    IncomingTextMessage,
    IntentResult,
    NoteRead,
    ReminderRead,
)
from app.schemas.dialog_state import DialogStateRead
from app.services import IncomingMessageService
from app.services.incoming_message_responses import reminder_created_text


def run(coro):
    return asyncio.run(coro)


class FakeAiService:
    def __init__(self, result: IntentResult) -> None:
        self.result = result
        self.calls = []

    async def interpret_message(self, input_data):
        self.calls.append(input_data)
        return self.result


class RaisingAiService(FakeAiService):
    async def interpret_message(self, input_data):
        self.calls.append(input_data)
        raise RuntimeError("AI unavailable")


class FakeNoteService:
    def __init__(self) -> None:
        self.created: list[CreateNoteInput] = []
        self.forwarded: list[CreateForwardedNoteInput] = []
        self.deleted: list[int] = []
        self.deleted_many: list[list[int]] = []
        self.deleted_categories: list[str] = []
        self.deleted_all = False
        self.note_count = 3
        self.category_count = 2
        self.listed = [make_note(note_id=11, content="First note")]
        self.category_names: list[str] = []

    async def create_note(self, data: CreateNoteInput) -> NoteRead:
        self.created.append(data)
        return make_note(
            note_id=1,
            content=data.content,
            language=data.language,
            category_name=data.category_name,
        )

    async def create_forwarded_text_note(
        self,
        data: CreateForwardedNoteInput,
    ) -> NoteRead:
        self.forwarded.append(data)
        return make_note(
            note_id=2,
            content=data.content,
            source_type="forwarded",
            category_name=data.category_name,
            source_chat_id=data.forward.source_chat_id,
            source_chat_title=data.forward.source_chat_title,
            source_message_id=data.forward.source_message_id,
            forward_sender_name=data.forward.forward_sender_name,
        )

    async def list_notes(self, *, telegram_id: int, limit: int = 20) -> list[NoteRead]:
        return self.listed

    async def list_category_names(self, *, telegram_id: int) -> list[str]:
        return self.category_names

    async def delete_note(self, *, telegram_id: int, note_id: int) -> None:
        self.deleted.append(note_id)

    async def count_notes(self, *, telegram_id: int) -> int:
        return self.note_count

    async def count_notes_by_category(
        self,
        *,
        telegram_id: int,
        category_name: str,
    ) -> int:
        return self.category_count

    async def count_existing_notes_by_ids(
        self,
        *,
        telegram_id: int,
        note_ids: list[int],
    ) -> int:
        if self.note_count <= 0:
            return 0
        return len(note_ids)

    async def delete_notes_by_ids(
        self,
        *,
        telegram_id: int,
        note_ids: list[int],
    ) -> int:
        self.deleted_many.append(note_ids)
        return len(note_ids)

    async def delete_notes_by_category(
        self,
        *,
        telegram_id: int,
        category_name: str,
    ) -> int:
        self.deleted_categories.append(category_name)
        return self.category_count

    async def delete_all_notes(self, *, telegram_id: int) -> int:
        self.deleted_all = True
        return self.note_count


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
        self.active: DialogStateRead | None = None
        self.completed = False

    async def create_dialog_state(self, data: CreateDialogStateInput):
        self.created.append(data)
        return None

    async def get_active_dialog_state(self, *, telegram_id: int):
        return self.active

    async def complete_dialog_state(self, *, telegram_id: int):
        self.completed = True
        self.active = None
        return None

    async def cancel_dialog_state(self, *, telegram_id: int):
        self.completed = False
        self.active = None
        return None


class FakeReminderScheduler:
    def __init__(self) -> None:
        self.scheduled: list[tuple[int, datetime]] = []

    def schedule_reminder(self, reminder_id: int, remind_at_utc: datetime) -> None:
        self.scheduled.append((reminder_id, remind_at_utc))


def make_service(
    intent: IntentResult,
    *,
    ai_service: FakeAiService | None = None,
    note_service: FakeNoteService | None = None,
    reminder_service: FakeReminderService | None = None,
    dialog_service: FakeDialogService | None = None,
    reminder_scheduler: FakeReminderScheduler | None = None,
) -> tuple[IncomingMessageService, FakeAiService, FakeNoteService, FakeReminderService, FakeDialogService]:
    ai_service = ai_service or FakeAiService(intent)
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
    category_id: int | None = None,
    category_name: str | None = None,
    source_chat_id: int | None = None,
    source_chat_title: str | None = None,
    source_message_id: int | None = None,
    forward_sender_name: str | None = None,
) -> NoteRead:
    now = datetime.now(timezone.utc)
    return NoteRead(
        id=note_id,
        user_id=10,
        category_id=category_id,
        category_name=category_name,
        title=None,
        content=content,
        source_type=source_type,
        source_chat_id=source_chat_id,
        source_chat_title=source_chat_title,
        source_message_id=source_message_id,
        forward_sender_name=forward_sender_name,
        language=language,
        created_at=now,
        updated_at=now,
    )


def make_reminder(
    *,
    reminder_id: int,
    text: str,
    remind_at: datetime | None = None,
    timezone_name: str = "UTC",
) -> ReminderRead:
    return ReminderRead(
        id=reminder_id,
        user_id=10,
        text=text,
        remind_at_utc=remind_at or datetime.now(timezone.utc) + timedelta(hours=1),
        timezone=timezone_name,
        status="scheduled",
        created_at=datetime.now(timezone.utc),
        sent_at=None,
        error_text=None,
    )


def test_reminder_created_text_for_today() -> None:
    reminder = make_reminder(
        reminder_id=1,
        text="закрыть дверь",
        remind_at=datetime(2026, 7, 28, 15, 35, tzinfo=timezone.utc),
        timezone_name="Europe/Moscow",
    )

    text = reminder_created_text(
        reminder,
        "ru",
        now=datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc),
    )

    assert text == "Готово, создал напоминание на 18:35."


def test_reminder_created_text_for_other_day_in_current_year() -> None:
    reminder = make_reminder(
        reminder_id=1,
        text="закрыть дверь",
        remind_at=datetime(2026, 7, 30, 15, 35, tzinfo=timezone.utc),
        timezone_name="Europe/Moscow",
    )

    text = reminder_created_text(
        reminder,
        "ru",
        now=datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc),
    )

    assert text == "Готово, создал напоминание на 30.07 в 18:35."


def test_reminder_created_text_for_other_year() -> None:
    reminder = make_reminder(
        reminder_id=1,
        text="закрыть дверь",
        remind_at=datetime(2027, 7, 30, 15, 35, tzinfo=timezone.utc),
        timezone_name="Europe/Moscow",
    )

    text = reminder_created_text(
        reminder,
        "ru",
        now=datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc),
    )

    assert text == "Готово, создал напоминание на 30.07.2027 в 18:35."


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


def test_incoming_service_creates_note_with_explicit_category() -> None:
    async def scenario() -> None:
        service, _, notes, _, dialogs = make_service(
            IntentResult(
                intent="create_note",
                parameters={"content": "https://ozon.ru/item", "category_name": "Shopping"},
            )
        )

        result = await service.handle_text_message(make_message("Save to shopping"))

        assert result.text == "Done, saved note #1."
        assert notes.created[0].category_name == "Shopping"
        assert dialogs.created == []

    run(scenario())


def test_incoming_service_passes_known_categories_to_ai() -> None:
    async def scenario() -> None:
        notes = FakeNoteService()
        notes.category_names = ["Shopping"]
        service, ai, created_notes, _, _ = make_service(
            IntentResult(
                intent="create_note",
                parameters={
                    "content": "https://ozon.ru/next",
                    "category_name": "Shopping",
                },
            ),
            note_service=notes,
        )

        await service.handle_text_message(make_message("Save this OZON link"))

        assert ai.calls[0].known_categories == ["Shopping"]
        assert created_notes.created[0].category_name == "Shopping"

    run(scenario())


def test_incoming_service_asks_for_category_when_ai_needs_it() -> None:
    async def scenario() -> None:
        service, _, notes, _, dialogs = make_service(
            IntentResult(
                intent="create_note",
                parameters={"content": "https://example.com", "missing_fields": ["category"]},
                clarification_question="Which category?",
            )
        )

        result = await service.handle_text_message(make_message("Save this link"))

        assert result.text == "Which category?"
        assert notes.created == []
        assert dialogs.created[0].state_type == "create_note_category"
        assert dialogs.created[0].payload["missing_fields"] == ["category"]

    run(scenario())


def test_incoming_service_completes_category_dialog() -> None:
    async def scenario() -> None:
        dialogs = FakeDialogService()
        now = datetime.now(timezone.utc)
        dialogs.active = DialogStateRead(
            id=1,
            user_id=10,
            state_type="create_note_category",
            status="active",
            payload={
                "original_text": "https://ozon.ru/item save it",
                "parameters": {"content": "https://ozon.ru/item"},
                "missing_fields": ["category"],
            },
            expires_at=None,
            created_at=now,
            updated_at=now,
        )
        service, ai, notes, _, _ = make_service(
            IntentResult(intent="unknown"),
            dialog_service=dialogs,
        )

        result = await service.handle_text_message(make_message("Shopping"))

        assert result.text == "Done, saved note #1."
        assert ai.calls == []
        assert notes.created[0].content == "https://ozon.ru/item"
        assert notes.created[0].category_name == "Shopping"
        assert dialogs.completed is True

    run(scenario())


def test_incoming_service_saves_forwarded_text_with_ai_category_name() -> None:
    async def scenario() -> None:
        notes = FakeNoteService()
        notes.category_names = ["Shopping"]
        service, ai, created_notes, _, _ = make_service(
            IntentResult(
                intent="create_note",
                parameters={"category_name": "Shopping"},
            ),
            note_service=notes,
        )

        result = await service.handle_text_message(
            IncomingTextMessage(
                telegram_id=42,
                text="https://ozon.ru/item",
                language="en",
                timezone="UTC",
                source_type="forwarded",
                forward=ForwardInfo(
                    source_chat_id=55,
                    source_chat_title="Deals",
                    source_message_id=77,
                    forward_sender_name="OZON",
                ),
            )
        )

        assert result.text == "Done, saved the forwarded message as note #2."
        assert ai.calls[0].text == "https://ozon.ru/item"
        assert ai.calls[0].source_type == "forwarded"
        assert ai.calls[0].known_categories == ["Shopping"]
        assert created_notes.created == []
        assert created_notes.forwarded[0].content == "https://ozon.ru/item"
        assert created_notes.forwarded[0].category_name == "Shopping"
        assert created_notes.forwarded[0].forward.source_chat_id == 55
        assert created_notes.forwarded[0].forward.source_chat_title == "Deals"
        assert created_notes.forwarded[0].forward.source_message_id == 77
        assert created_notes.forwarded[0].forward.forward_sender_name == "OZON"

    run(scenario())


def test_incoming_service_saves_forwarded_text_without_category_on_unknown_ai() -> None:
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
        assert len(ai.calls) == 1
        assert notes.forwarded[0].content == "Forwarded text"
        assert notes.forwarded[0].category_name is None

    run(scenario())


def test_incoming_service_creates_forwarded_category_clarification() -> None:
    async def scenario() -> None:
        service, _, notes, _, dialogs = make_service(
            IntentResult(
                intent="create_note",
                parameters={"missing_fields": ["category"]},
                clarification_question="Which category?",
            )
        )

        result = await service.handle_text_message(
            IncomingTextMessage(
                telegram_id=42,
                text="Forwarded link",
                language="en",
                source_type="forwarded",
                forward=ForwardInfo(
                    source_chat_id=55,
                    source_chat_title="Deals",
                    source_message_id=77,
                    forward_sender_name="OZON",
                ),
            )
        )

        assert result.text == "Which category?"
        assert notes.forwarded == []
        assert dialogs.created[0].state_type == "create_note_category"
        assert dialogs.created[0].payload["source_type"] == "forwarded"
        assert dialogs.created[0].payload["original_text"] == "Forwarded link"
        assert dialogs.created[0].payload["forward"] == {
            "source_chat_id": 55,
            "source_chat_title": "Deals",
            "source_message_id": 77,
            "forward_sender_name": "OZON",
        }

    run(scenario())


def test_incoming_service_completes_forwarded_category_dialog_with_metadata() -> None:
    async def scenario() -> None:
        dialogs = FakeDialogService()
        now = datetime.now(timezone.utc)
        dialogs.active = DialogStateRead(
            id=1,
            user_id=10,
            state_type="create_note_category",
            status="active",
            payload={
                "original_text": "https://ozon.ru/item",
                "source_type": "forwarded",
                "forward": {
                    "source_chat_id": 55,
                    "source_chat_title": "Deals",
                    "source_message_id": 77,
                    "forward_sender_name": "OZON",
                },
                "parameters": {
                    "content": "AI-normalized text should not replace original",
                    "missing_fields": ["category"],
                },
                "missing_fields": ["category"],
            },
            expires_at=None,
            created_at=now,
            updated_at=now,
        )
        service, ai, notes, _, _ = make_service(
            IntentResult(intent="unknown"),
            dialog_service=dialogs,
        )

        result = await service.handle_text_message(make_message("Shopping"))

        assert result.text == "Done, saved the forwarded message as note #2."
        assert ai.calls == []
        assert notes.created == []
        forwarded = notes.forwarded[0]
        assert forwarded.content == "https://ozon.ru/item"
        assert forwarded.category_name == "Shopping"
        assert forwarded.forward.source_chat_id == 55
        assert forwarded.forward.source_chat_title == "Deals"
        assert forwarded.forward.source_message_id == 77
        assert forwarded.forward.forward_sender_name == "OZON"
        assert dialogs.completed is True

    run(scenario())


def test_incoming_service_saves_forwarded_text_when_ai_fails() -> None:
    async def scenario() -> None:
        ai_service = RaisingAiService(IntentResult(intent="unknown"))
        service, ai, notes, _, _ = make_service(
            IntentResult(intent="unknown"),
            ai_service=ai_service,
        )

        result = await service.handle_text_message(
            IncomingTextMessage(
                telegram_id=42,
                text="Forwarded text",
                language="en",
                source_type="forwarded",
                forward=ForwardInfo(forward_sender_name="Alice"),
            )
        )

        assert result.text == "Done, saved the forwarded message as note #2."
        assert len(ai.calls) == 1
        assert notes.forwarded[0].content == "Forwarded text"
        assert notes.forwarded[0].category_name is None
        assert notes.forwarded[0].forward.forward_sender_name == "Alice"

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


def test_bulk_delete_ids_creates_confirmation_and_deletes_nothing_before_yes() -> None:
    async def scenario() -> None:
        service, _, notes, _, dialogs = make_service(
            IntentResult(
                intent="delete_note",
                parameters={"delete_scope": "ids", "note_ids": [1, 3, 7]},
            )
        )

        result = await service.handle_text_message(make_message("delete notes 1, 3, 7"))

        assert result.text == "Delete? Yes/No"
        assert notes.deleted_many == []
        assert dialogs.created[0].state_type == "confirm_delete_notes"
        assert dialogs.created[0].payload == {
            "operation_type": "delete_note_ids",
            "count_preview": 3,
            "note_ids": [1, 3, 7],
        }

    run(scenario())


def test_bulk_delete_ids_returns_not_found_without_confirmation() -> None:
    async def scenario() -> None:
        notes = FakeNoteService()
        notes.note_count = 0
        service, _, created_notes, _, dialogs = make_service(
            IntentResult(
                intent="delete_note",
                parameters={"delete_scope": "ids", "note_ids": [1, 3, 7]},
            ),
            note_service=notes,
        )

        result = await service.handle_text_message(make_message("delete notes 1, 3, 7"))

        assert result.text == "I could not find those notes."
        assert created_notes.deleted_many == []
        assert dialogs.created == []

    run(scenario())


def test_bulk_delete_ids_yes_deletes_pending_notes_only() -> None:
    async def scenario() -> None:
        dialogs = FakeDialogService()
        now = datetime.now(timezone.utc)
        dialogs.active = DialogStateRead(
            id=1,
            user_id=10,
            state_type="confirm_delete_notes",
            status="active",
            payload={
                "operation_type": "delete_note_ids",
                "count_preview": 3,
                "note_ids": [1, 3, 7],
            },
            expires_at=None,
            created_at=now,
            updated_at=now,
        )
        service, ai, notes, _, _ = make_service(
            IntentResult(intent="unknown"),
            dialog_service=dialogs,
        )

        result = await service.handle_text_message(make_message("Yes"))

        assert result.text == "Deleted 3 note(s)."
        assert ai.calls == []
        assert notes.deleted_many == [[1, 3, 7]]
        assert dialogs.completed is True

    run(scenario())


def test_bulk_delete_no_cancels_pending_operation() -> None:
    async def scenario() -> None:
        dialogs = FakeDialogService()
        now = datetime.now(timezone.utc)
        dialogs.active = DialogStateRead(
            id=1,
            user_id=10,
            state_type="confirm_delete_notes",
            status="active",
            payload={
                "operation_type": "delete_note_ids",
                "count_preview": 2,
                "note_ids": [1, 2],
            },
            expires_at=None,
            created_at=now,
            updated_at=now,
        )
        service, _, notes, _, _ = make_service(
            IntentResult(intent="unknown"),
            dialog_service=dialogs,
        )

        result = await service.handle_text_message(make_message("No"))

        assert result.text == "Deletion cancelled."
        assert notes.deleted_many == []
        assert dialogs.active is None

    run(scenario())


def test_bulk_delete_invalid_confirmation_answer_keeps_dialog() -> None:
    async def scenario() -> None:
        dialogs = FakeDialogService()
        now = datetime.now(timezone.utc)
        dialogs.active = DialogStateRead(
            id=1,
            user_id=10,
            state_type="confirm_delete_notes",
            status="active",
            payload={
                "operation_type": "delete_note_ids",
                "count_preview": 1,
                "note_ids": [1],
            },
            expires_at=None,
            created_at=now,
            updated_at=now,
        )
        service, _, notes, _, _ = make_service(
            IntentResult(intent="unknown"),
            dialog_service=dialogs,
        )

        result = await service.handle_text_message(make_message("maybe"))

        assert result.text == 'Please answer "Yes" or "No".'
        assert notes.deleted_many == []
        assert dialogs.active is not None

    run(scenario())


def test_delete_category_notes_creates_confirmation_and_yes_deletes_category_notes() -> None:
    async def scenario() -> None:
        service, _, notes, _, dialogs = make_service(
            IntentResult(
                intent="delete_note",
                parameters={
                    "delete_scope": "category",
                    "category_name": "Shopping",
                },
            )
        )

        result = await service.handle_text_message(
            make_message("delete Shopping category notes")
        )

        assert result.text == "Delete? Yes/No"
        assert notes.deleted_categories == []
        assert dialogs.created[0].payload == {
            "operation_type": "delete_notes_by_category",
            "count_preview": 2,
            "category_name": "Shopping",
        }

        now = datetime.now(timezone.utc)
        dialogs.active = DialogStateRead(
            id=1,
            user_id=10,
            state_type="confirm_delete_notes",
            status="active",
            payload=dialogs.created[0].payload,
            expires_at=None,
            created_at=now,
            updated_at=now,
        )

        confirmed = await service.handle_text_message(make_message("Yes"))

        assert confirmed.text == 'Deleted 2 note(s) from category "Shopping".'
        assert notes.deleted_categories == ["Shopping"]

    run(scenario())


def test_delete_all_notes_creates_confirmation_and_yes_deletes_all_user_notes() -> None:
    async def scenario() -> None:
        notes = FakeNoteService()
        notes.note_count = 4
        service, _, created_notes, _, dialogs = make_service(
            IntentResult(
                intent="delete_note",
                parameters={"delete_scope": "all", "delete_all": True},
            ),
            note_service=notes,
        )

        result = await service.handle_text_message(make_message("delete all notes"))

        assert result.text == "Delete? Yes/No"
        assert created_notes.deleted_all is False
        assert dialogs.created[0].payload == {
            "operation_type": "delete_all_notes",
            "count_preview": 4,
            "delete_all": True,
        }

        now = datetime.now(timezone.utc)
        dialogs.active = DialogStateRead(
            id=1,
            user_id=10,
            state_type="confirm_delete_notes",
            status="active",
            payload=dialogs.created[0].payload,
            expires_at=None,
            created_at=now,
            updated_at=now,
        )

        confirmed = await service.handle_text_message(make_message("Yes"))

        assert confirmed.text == "Deleted all notes: 4."
        assert created_notes.deleted_all is True

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
        assert result.text.startswith("Done, created reminder")
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


def test_incoming_service_maps_create_reminder_with_relative_datetime() -> None:
    async def scenario() -> None:
        scheduler = FakeReminderScheduler()
        service, _, _, reminders, dialogs = make_service(
            IntentResult(
                intent="create_reminder",
                parameters={
                    "text": "Call mom",
                    "remind_at": "in 2 minutes",
                },
            ),
            reminder_scheduler=scheduler,
        )

        result = await service.handle_text_message(make_message("Remind me"))

        assert result.intent == "create_reminder"
        assert result.text.startswith("Done, created reminder")
        assert reminders.created[0].text == "Call mom"
        delta = reminders.created[0].remind_at - datetime.now(timezone.utc)
        assert 0 < delta.total_seconds() <= 130
        assert scheduler.scheduled == [(3, reminders.created[0].remind_at)]
        assert dialogs.created == []

    run(scenario())


def test_incoming_service_maps_create_reminder_with_russian_relative_datetime() -> None:
    async def scenario() -> None:
        scheduler = FakeReminderScheduler()
        service, _, _, reminders, dialogs = make_service(
            IntentResult(
                intent="create_reminder",
                parameters={
                    "text": "позвонить маме",
                    "remind_at": "через 2 минуты",
                },
            ),
            reminder_scheduler=scheduler,
        )

        result = await service.handle_text_message(make_message("напомни мне"))

        assert result.intent == "create_reminder"
        assert result.text.startswith("Done, created reminder")
        assert reminders.created[0].text == "позвонить маме"
        delta = reminders.created[0].remind_at - datetime.now(timezone.utc)
        assert 0 < delta.total_seconds() <= 130
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
