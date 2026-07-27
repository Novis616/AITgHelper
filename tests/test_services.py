from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
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


def test_note_service_creates_forwarded_text_note(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            service = NoteService(session)

            note = await service.create_forwarded_text_note(
                CreateForwardedNoteInput(
                    telegram_id=1002,
                    content="Forwarded insight",
                    forward=ForwardInfo(
                        source_chat_id=55,
                        source_chat_title="Source chat",
                        source_message_id=77,
                        forward_sender_name="Alice",
                    ),
                )
            )

            assert note.source_type == "forwarded"
            assert note.source_chat_id == 55
            assert note.source_chat_title == "Source chat"
            assert note.source_message_id == 77
            assert note.forward_sender_name == "Alice"
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
                    remind_at=datetime(2026, 7, 28, 18, 0),
                )
            )

            assert reminder.timezone == "Europe/Moscow"
            assert reminder.remind_at_utc == datetime(
                2026,
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

            cancelled = await service.cancel_reminder(
                telegram_id=2002,
                reminder_id=reminder.id,
            )
            assert cancelled.status == "cancelled"
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
