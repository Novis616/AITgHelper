from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Base
from app.repositories import (
    AiRequestLogRepository,
    DialogStateRepository,
    NoteCategoryRepository,
    NoteRepository,
    ReminderRepository,
    UserRepository,
)
from app.repositories.database import create_engine, create_session_factory


def run(coro):
    return asyncio.run(coro)


async def make_session(tmp_path: Path) -> AsyncSession:
    database_path = tmp_path / "repositories.sqlite3"
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


def test_user_repository_get_or_create(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            repo = UserRepository(session)

            user = await repo.get_or_create(
                telegram_id=1001,
                language="en",
                timezone="UTC",
            )
            same_user = await repo.get_or_create(telegram_id=1001)

            assert user.id == same_user.id
            assert user.language == "en"
            assert user.timezone == "UTC"
        finally:
            await close_session(session)

    run(scenario())


def test_note_repository_create_list_and_delete(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            users = UserRepository(session)
            notes = NoteRepository(session)
            user = await users.create(telegram_id=2001)

            note = await notes.create(
                user_id=user.id,
                title="Idea",
                content="Build the notes flow",
                source_type="forwarded",
                source_chat_id=55,
                source_message_id=77,
                forward_sender_name="Alice",
            )
            await session.commit()

            listed = await notes.list_for_user(user.id)
            assert [item.id for item in listed] == [note.id]
            assert listed[0].source_type == "forwarded"

            await notes.delete(note)
            await session.commit()

            assert await notes.get_by_id(note.id) is None
        finally:
            await close_session(session)

    run(scenario())


def test_note_category_repository_normalizes_names(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            users = UserRepository(session)
            categories = NoteCategoryRepository(session)
            user = await users.create(telegram_id=2002)

            first = await categories.get_or_create(
                user_id=user.id,
                name="  Shopping   Links ",
            )
            second = await categories.get_or_create(
                user_id=user.id,
                name="shopping links",
            )
            await session.commit()

            assert first.id == second.id
            assert first.name == "Shopping Links"
            assert first.normalized_name == "shopping links"
        finally:
            await close_session(session)

    run(scenario())


def test_reminder_repository_status_and_due_queries(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            users = UserRepository(session)
            reminders = ReminderRepository(session)
            user = await users.create(telegram_id=3001)
            now = datetime.now(timezone.utc)

            due = await reminders.create(
                user_id=user.id,
                text="Due soon",
                remind_at_utc=now - timedelta(minutes=1),
                timezone="Europe/Moscow",
            )
            future = await reminders.create(
                user_id=user.id,
                text="Later",
                remind_at_utc=now + timedelta(hours=1),
                timezone="Europe/Moscow",
            )
            await session.commit()

            due_items = await reminders.list_scheduled_due_before(now)
            future_items = await reminders.list_future_scheduled_after(now)
            assert [item.id for item in due_items] == [due.id]
            assert [item.id for item in future_items] == [future.id]

            await reminders.mark_sent(due)
            await reminders.cancel(future)
            await session.commit()

            assert due.status == "sent"
            assert due.sent_at is not None
            assert future.status == "cancelled"
        finally:
            await close_session(session)

    run(scenario())


def test_dialog_state_repository_active_state_lifecycle(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            users = UserRepository(session)
            states = DialogStateRepository(session)
            user = await users.create(telegram_id=4001)

            state = await states.create(
                user_id=user.id,
                state_type="create_reminder",
                payload={"missing_fields": ["date"]},
            )
            await session.commit()

            active = await states.get_active_for_user(user.id)
            assert active is not None
            assert active.id == state.id

            await states.update_payload(state, {"missing_fields": []})
            await states.complete(state)
            await session.commit()

            assert await states.get_active_for_user(user.id) is None
        finally:
            await close_session(session)

    run(scenario())


def test_ai_request_log_repository_create_and_list(tmp_path: Path) -> None:
    async def scenario() -> None:
        session = await make_session(tmp_path)
        try:
            users = UserRepository(session)
            logs = AiRequestLogRepository(session)
            user = await users.create(telegram_id=5001)

            log = await logs.create(
                user_id=user.id,
                provider="openai",
                model="test-model",
                user_text="Save this idea",
                prompt="Interpret intent",
                raw_response='{"intent":"create_note"}',
                normalized_intent="create_note",
                confidence=0.91,
            )
            await session.commit()

            listed = await logs.list_for_user(user.id)
            assert [item.id for item in listed] == [log.id]
            assert listed[0].normalized_intent == "create_note"
            assert listed[0].error_text is None
        finally:
            await close_session(session)

    run(scenario())
