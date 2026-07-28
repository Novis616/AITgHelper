from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import NotFoundError, ValidationError
from app.config.settings import Settings
from app.models import Base
from app.repositories.database import create_engine, create_session_factory
from app.schemas import (
    CreateDialogStateInput,
    CreateForwardedNoteInput,
    CreateNoteInput,
    CreateReminderInput,
    ForwardInfo,
)
from app.services import DialogService, NoteService, ReminderService


def run(coro):
    return asyncio.run(coro)


async def make_session(tmp_path: Path) -> AsyncSession:
    database_path = tmp_path / "services.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    session = session_factory()
    session.info["engine"] = engine
    return session


async def close_session(session: AsyncSession) -> None:
    engine = session.info["engine"]
    await session.close()
    await engine.dispose()


def test_note_service_creates_lists_and_deletes_plain_note(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = NoteService(session)

            note = await service.create_note(
                CreateNoteInput(
                    telegram_id=1001,
                    title="  Idea  ",
                    content="  Build service layer  ",
                    language="en",
                )
            )

            assert note.title == "Idea"
            assert note.content == "Build service layer"
            assert note.source_type == "plain"
            assert note.language == "en"

            listed = await service.list_notes(telegram_id=1001)
            assert [item.id for item in listed] == [note.id]

            await service.delete_note(telegram_id=1001, note_id=note.id)
            assert await service.list_notes(telegram_id=1001) == []
        finally:
            await close_session(session)

    run(scenario())


def test_note_service_stores_ciphertext_and_returns_plaintext(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = NoteService(session)
            secret_content = "private note body"
            secret_title = "private title"

            note = await service.create_note(
                CreateNoteInput(
                    telegram_id=1010,
                    title=secret_title,
                    content=secret_content,
                )
            )

            assert note.title == secret_title
            assert note.content == secret_content

            row = (
                await session.execute(
                    text("SELECT title, content FROM notes WHERE id = :id"),
                    {"id": note.id},
                )
            ).mappings().one()
            assert row["title"].startswith("enc:v1:")
            assert row["content"].startswith("enc:v1:")
            assert secret_title not in row["title"]
            assert secret_content not in row["content"]
        finally:
            await close_session(session)

    run(scenario())


def test_note_service_lists_notes_oldest_first(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = NoteService(session)

            first = await service.create_note(
                CreateNoteInput(telegram_id=1011, content="First")
            )
            second = await service.create_note(
                CreateNoteInput(telegram_id=1011, content="Second")
            )

            listed = await service.list_notes(telegram_id=1011)

            assert [item.id for item in listed] == [first.id, second.id]
            assert [item.content for item in listed] == ["First", "Second"]
        finally:
            await close_session(session)

    run(scenario())


def test_note_service_creates_and_reuses_category(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = NoteService(session)

            first = await service.create_note(
                CreateNoteInput(
                    telegram_id=1012,
                    content="https://ozon.ru/first",
                    category_name="  Shopping  ",
                    language="en",
                )
            )
            second = await service.create_note(
                CreateNoteInput(
                    telegram_id=1012,
                    content="https://ozon.ru/second",
                    category_name="shopping",
                    language="en",
                )
            )

            assert first.category_id is not None
            assert second.category_id == first.category_id
            assert first.category_name == "Shopping"
            assert second.category_name == "Shopping"
            assert await service.list_category_names(telegram_id=1012) == ["Shopping"]
        finally:
            await close_session(session)

    run(scenario())


def test_note_service_same_category_name_is_independent_per_user(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = NoteService(session)

            first = await service.create_note(
                CreateNoteInput(
                    telegram_id=1013,
                    content="First shopping note",
                    category_name="Shopping",
                )
            )
            second = await service.create_note(
                CreateNoteInput(
                    telegram_id=1014,
                    content="Second shopping note",
                    category_name="shopping",
                )
            )

            assert first.category_name == "Shopping"
            assert second.category_name == "shopping"
            assert first.category_id != second.category_id
            assert await service.list_category_names(telegram_id=1013) == ["Shopping"]
            assert await service.list_category_names(telegram_id=1014) == ["shopping"]
        finally:
            await close_session(session)

    run(scenario())


def test_note_service_creates_forwarded_text_note(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = NoteService(session)

            note = await service.create_forwarded_text_note(
                CreateForwardedNoteInput(
                    telegram_id=1002,
                    content="Forwarded insight",
                    category_name="Inbox",
                    forward=ForwardInfo(
                        source_chat_id=55,
                        source_chat_title="Source chat",
                        source_message_id=77,
                        forward_sender_name="Alice",
                    ),
                )
            )

            assert note.source_type == "forwarded"
            assert note.category_name == "Inbox"
            assert note.source_chat_id == 55
            assert note.source_chat_title == "Source chat"
            assert note.source_message_id == 77
            assert note.forward_sender_name == "Alice"
        finally:
            await close_session(session)

    run(scenario())


def test_note_service_does_not_list_foreign_notes(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = NoteService(session)

            own = await service.create_note(
                CreateNoteInput(telegram_id=1004, content="Own note")
            )
            foreign = await service.create_note(
                CreateNoteInput(telegram_id=1005, content="Foreign note")
            )

            own_notes = await service.list_notes(telegram_id=1004)
            foreign_notes = await service.list_notes(telegram_id=1005)

            assert [note.id for note in own_notes] == [own.id]
            assert [note.id for note in foreign_notes] == [foreign.id]
        finally:
            await close_session(session)

    run(scenario())


def test_note_service_rejects_empty_content_and_foreign_delete(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = NoteService(session)

            with pytest.raises(ValidationError):
                await service.create_note(
                    CreateNoteInput(telegram_id=1003, content="   ")
                )

            note = await service.create_note(
                CreateNoteInput(telegram_id=1003, content="Keep me")
            )
            with pytest.raises(NotFoundError):
                await service.delete_note(telegram_id=9999, note_id=note.id)

            assert [item.id for item in await service.list_notes(telegram_id=1003)] == [
                note.id
            ]
        finally:
            await close_session(session)

    run(scenario())


def test_note_service_bulk_deletes_ids_only_for_current_user(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = NoteService(session)

            first = await service.create_note(
                CreateNoteInput(telegram_id=1101, content="First")
            )
            second = await service.create_note(
                CreateNoteInput(telegram_id=1101, content="Second")
            )
            foreign = await service.create_note(
                CreateNoteInput(telegram_id=9999, content="Foreign")
            )

            with pytest.raises(NotFoundError):
                await service.delete_notes_by_ids(
                    telegram_id=1101,
                    note_ids=[first.id, foreign.id],
                )

            assert await service.count_existing_notes_by_ids(
                telegram_id=1101,
                note_ids=[first.id, foreign.id],
            ) == 0
            assert [note.id for note in await service.list_notes(telegram_id=1101)] == [
                first.id,
                second.id,
            ]
            assert [note.id for note in await service.list_notes(telegram_id=9999)] == [
                foreign.id
            ]
            assert await service.count_existing_notes_by_ids(
                telegram_id=1101,
                note_ids=[first.id, second.id],
            ) == 2

            deleted_count = await service.delete_notes_by_ids(
                telegram_id=1101,
                note_ids=[first.id, second.id],
            )

            assert deleted_count == 2
            assert await service.list_notes(telegram_id=1101) == []
            assert [note.id for note in await service.list_notes(telegram_id=9999)] == [
                foreign.id
            ]
        finally:
            await close_session(session)

    run(scenario())


def test_note_service_deletes_category_notes_but_keeps_category(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = NoteService(session)

            await service.create_note(
                CreateNoteInput(
                    telegram_id=1102,
                    content="Buy milk",
                    category_name="Shopping",
                )
            )
            await service.create_note(
                CreateNoteInput(
                    telegram_id=1102,
                    content="Buy bread",
                    category_name="shopping",
                )
            )
            keep = await service.create_note(
                CreateNoteInput(
                    telegram_id=1102,
                    content="Project idea",
                    category_name="Ideas",
                )
            )
            foreign = await service.create_note(
                CreateNoteInput(
                    telegram_id=9999,
                    content="Foreign shopping",
                    category_name="Shopping",
                )
            )

            assert await service.count_notes_by_category(
                telegram_id=1102,
                category_name=" shopping ",
            ) == 2

            deleted_count = await service.delete_notes_by_category(
                telegram_id=1102,
                category_name="shopping",
            )

            assert deleted_count == 2
            assert [note.id for note in await service.list_notes(telegram_id=1102)] == [
                keep.id
            ]
            assert [note.id for note in await service.list_notes(telegram_id=9999)] == [
                foreign.id
            ]
            assert await service.list_category_names(telegram_id=1102) == [
                "Ideas",
                "Shopping",
            ]
        finally:
            await close_session(session)

    run(scenario())


def test_note_service_deletes_all_notes_only_for_current_user(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = NoteService(session)

            await service.create_note(CreateNoteInput(telegram_id=1103, content="One"))
            await service.create_note(CreateNoteInput(telegram_id=1103, content="Two"))
            foreign = await service.create_note(
                CreateNoteInput(telegram_id=9999, content="Foreign")
            )

            assert await service.count_notes(telegram_id=1103) == 2

            deleted_count = await service.delete_all_notes(telegram_id=1103)

            assert deleted_count == 2
            assert await service.list_notes(telegram_id=1103) == []
            assert [note.id for note in await service.list_notes(telegram_id=9999)] == [
                foreign.id
            ]
        finally:
            await close_session(session)

    run(scenario())


def test_reminder_service_converts_user_time_to_utc(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = ReminderService(
                session,
                settings=Settings(default_timezone="Europe/Moscow"),
            )

            reminder = await service.create_reminder(
                CreateReminderInput(
                    telegram_id=2001,
                    text="Buy groceries",
                    remind_at=datetime(2027, 7, 28, 18, 0),
                )
            )

            assert reminder.timezone == "Europe/Moscow"
            assert reminder.remind_at_utc == datetime(
                2027,
                7,
                28,
                15,
                0,
                tzinfo=timezone.utc,
            )
            assert reminder.status == "scheduled"
        finally:
            await close_session(session)

    run(scenario())


def test_reminder_service_stores_ciphertext_and_returns_plaintext(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = ReminderService(
                session,
                settings=Settings(default_timezone="UTC"),
            )
            secret_text = "call the doctor"

            reminder = await service.create_reminder(
                CreateReminderInput(
                    telegram_id=2010,
                    text=secret_text,
                    remind_at=datetime.now(timezone.utc) + timedelta(hours=1),
                )
            )

            assert reminder.text == secret_text

            row = (
                await session.execute(
                    text("SELECT text FROM reminders WHERE id = :id"),
                    {"id": reminder.id},
                )
            ).mappings().one()
            assert row["text"].startswith("enc:v1:")
            assert secret_text not in row["text"]
        finally:
            await close_session(session)

    run(scenario())


def test_reminder_service_rejects_past_time_and_cancels_only_owner(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = ReminderService(
                session,
                settings=Settings(default_timezone="UTC"),
            )

            with pytest.raises(ValidationError):
                await service.create_reminder(
                    CreateReminderInput(
                        telegram_id=2002,
                        text="Too late",
                        remind_at=datetime.now(timezone.utc) - timedelta(minutes=1),
                    )
                )

            reminder = await service.create_reminder(
                CreateReminderInput(
                    telegram_id=2002,
                    text="Future",
                    remind_at=datetime.now(timezone.utc) + timedelta(hours=1),
                )
            )
            with pytest.raises(NotFoundError):
                await service.cancel_reminder(
                    telegram_id=9999,
                    reminder_id=reminder.id,
                )
            listed = await service.list_reminders(
                telegram_id=2002,
                status="scheduled",
            )
            assert [item.id for item in listed] == [reminder.id]

            cancelled = await service.cancel_reminder(
                telegram_id=2002,
                reminder_id=reminder.id,
            )
            assert cancelled.status == "cancelled"
        finally:
            await close_session(session)

    run(scenario())


def test_reminder_service_does_not_list_foreign_reminders(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = ReminderService(
                session,
                settings=Settings(default_timezone="UTC"),
            )

            own = await service.create_reminder(
                CreateReminderInput(
                    telegram_id=2003,
                    text="Own reminder",
                    remind_at=datetime.now(timezone.utc) + timedelta(hours=1),
                )
            )
            foreign = await service.create_reminder(
                CreateReminderInput(
                    telegram_id=2004,
                    text="Foreign reminder",
                    remind_at=datetime.now(timezone.utc) + timedelta(hours=2),
                )
            )

            own_reminders = await service.list_reminders(
                telegram_id=2003,
                status="scheduled",
            )
            foreign_reminders = await service.list_reminders(
                telegram_id=2004,
                status="scheduled",
            )

            assert [item.id for item in own_reminders] == [own.id]
            assert [item.id for item in foreign_reminders] == [foreign.id]
        finally:
            await close_session(session)

    run(scenario())


def test_reminder_service_bulk_cancels_ids_only_for_current_user(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = ReminderService(
                session,
                settings=Settings(default_timezone="UTC"),
            )

            first = await service.create_reminder(
                CreateReminderInput(
                    telegram_id=2101,
                    text="First",
                    remind_at=datetime.now(timezone.utc) + timedelta(hours=1),
                )
            )
            second = await service.create_reminder(
                CreateReminderInput(
                    telegram_id=2101,
                    text="Second",
                    remind_at=datetime.now(timezone.utc) + timedelta(hours=2),
                )
            )
            foreign = await service.create_reminder(
                CreateReminderInput(
                    telegram_id=9999,
                    text="Foreign",
                    remind_at=datetime.now(timezone.utc) + timedelta(hours=3),
                )
            )

            with pytest.raises(NotFoundError):
                await service.cancel_reminders_by_ids(
                    telegram_id=2101,
                    reminder_ids=[first.id, foreign.id],
                )

            assert await service.count_existing_scheduled_reminders_by_ids(
                telegram_id=2101,
                reminder_ids=[first.id, foreign.id],
            ) == 0
            assert await service.count_existing_scheduled_reminders_by_ids(
                telegram_id=2101,
                reminder_ids=[first.id, second.id],
            ) == 2

            cancelled_count = await service.cancel_reminders_by_ids(
                telegram_id=2101,
                reminder_ids=[first.id, second.id],
            )

            assert cancelled_count == 2
            assert await service.list_reminders(
                telegram_id=2101,
                status="scheduled",
            ) == []
            foreign_reminders = await service.list_reminders(
                telegram_id=9999,
                status="scheduled",
            )
            assert [item.id for item in foreign_reminders] == [foreign.id]
        finally:
            await close_session(session)

    run(scenario())


def test_reminder_service_cancels_all_scheduled_only_for_current_user(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = ReminderService(
                session,
                settings=Settings(default_timezone="UTC"),
            )

            await service.create_reminder(
                CreateReminderInput(
                    telegram_id=2102,
                    text="One",
                    remind_at=datetime.now(timezone.utc) + timedelta(hours=1),
                )
            )
            await service.create_reminder(
                CreateReminderInput(
                    telegram_id=2102,
                    text="Two",
                    remind_at=datetime.now(timezone.utc) + timedelta(hours=2),
                )
            )
            foreign = await service.create_reminder(
                CreateReminderInput(
                    telegram_id=9999,
                    text="Foreign",
                    remind_at=datetime.now(timezone.utc) + timedelta(hours=3),
                )
            )

            assert await service.count_scheduled_reminders(telegram_id=2102) == 2

            cancelled_count = await service.cancel_all_scheduled_reminders(
                telegram_id=2102,
            )

            assert cancelled_count == 2
            assert await service.count_scheduled_reminders(telegram_id=2102) == 0
            foreign_reminders = await service.list_reminders(
                telegram_id=9999,
                status="scheduled",
            )
            assert [item.id for item in foreign_reminders] == [foreign.id]
        finally:
            await close_session(session)

    run(scenario())


def test_dialog_service_active_state_lifecycle(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = DialogService(
                session,
                settings=Settings(default_timezone="UTC"),
            )

            first = await service.create_dialog_state(
                CreateDialogStateInput(
                    telegram_id=3001,
                    state_type="create_reminder",
                    payload={"missing_fields": ["time"]},
                )
            )
            second = await service.create_dialog_state(
                CreateDialogStateInput(
                    telegram_id=3001,
                    state_type="create_note",
                    payload={"draft": "hello"},
                )
            )

            assert first.id != second.id
            active = await service.get_active_dialog_state(telegram_id=3001)
            assert active is not None
            assert active.id == second.id

            updated = await service.update_payload(
                telegram_id=3001,
                payload={"draft": "updated"},
            )
            assert updated.payload == {"draft": "updated"}

            completed = await service.complete_dialog_state(telegram_id=3001)
            assert completed.status == "completed"
            assert await service.get_active_dialog_state(telegram_id=3001) is None
        finally:
            await close_session(session)

    run(scenario())


def test_dialog_service_stores_encrypted_payload_and_returns_plaintext(
    tmp_path: Path,
) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = DialogService(
                session,
                settings=Settings(default_timezone="UTC"),
            )
            secret_payload = {"draft": "secret dialog text"}

            state = await service.create_dialog_state(
                CreateDialogStateInput(
                    telegram_id=3010,
                    state_type="create_note",
                    payload=secret_payload,
                )
            )

            assert state.payload == secret_payload

            row = (
                await session.execute(
                    text("SELECT payload FROM dialog_states WHERE id = :id"),
                    {"id": state.id},
                )
            ).mappings().one()
            assert row["payload"].startswith("enc:v1:")
            assert "secret dialog text" not in row["payload"]
        finally:
            await close_session(session)

    run(scenario())


def test_dialog_service_active_state_is_independent_per_user(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = DialogService(
                session,
                settings=Settings(default_timezone="UTC"),
            )

            first = await service.create_dialog_state(
                CreateDialogStateInput(
                    telegram_id=3002,
                    state_type="create_note_category",
                    payload={"draft": "first"},
                )
            )
            second = await service.create_dialog_state(
                CreateDialogStateInput(
                    telegram_id=3003,
                    state_type="confirm_delete_notes",
                    payload={"draft": "second"},
                )
            )

            assert first.user_id != second.user_id
            await service.complete_dialog_state(telegram_id=3003)

            first_active = await service.get_active_dialog_state(telegram_id=3002)
            second_active = await service.get_active_dialog_state(telegram_id=3003)

            assert first_active is not None
            assert first_active.id == first.id
            assert first_active.payload == {"draft": "first"}
            assert second_active is None
        finally:
            await close_session(session)

    run(scenario())


def test_encryption_key_is_required_when_enabled() -> None:
    with pytest.raises(PydanticValidationError):
        Settings(encryption_enabled=True, app_encryption_key="")


def test_encryption_key_must_be_valid_fernet_key() -> None:
    with pytest.raises(PydanticValidationError):
        Settings(encryption_enabled=True, app_encryption_key="not-a-fernet-key")
