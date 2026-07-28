from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Base
from app.repositories import ReminderRepository, UserRepository
from app.repositories.database import create_engine, create_session_factory
from app.scheduler import ReminderScheduler, send_reminder_job


def run(coro):
    return asyncio.run(coro)


class FakeBot:
    def __init__(self, *, error: Exception | None = None) -> None:
        self.error = error
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, *, chat_id: int, text: str) -> None:
        if self.error is not None:
            raise self.error
        self.messages.append((chat_id, text))


class FakeScheduler:
    def __init__(self) -> None:
        self.running = False
        self.jobs: list[dict[str, object]] = []

    def start(self) -> None:
        self.running = True

    def shutdown(self, *, wait: bool = True) -> None:
        self.running = False

    def add_job(self, func, **kwargs) -> None:
        self.jobs.append({"func": func, **kwargs})


async def make_session_factory(tmp_path: Path):
    database_path = tmp_path / "scheduler.sqlite3"
    engine = create_engine(f"sqlite+aiosqlite:///{database_path}")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    session_factory = create_session_factory(engine)
    return engine, session_factory


async def create_reminder(
    session: AsyncSession,
    *,
    telegram_id: int = 7001,
    text: str = "Buy milk",
    remind_at_utc: datetime,
) -> int:
    users = UserRepository(session)
    reminders = ReminderRepository(session)
    user = await users.create(telegram_id=telegram_id, timezone="UTC")
    reminder = await reminders.create(
        user_id=user.id,
        text=text,
        remind_at_utc=remind_at_utc,
        timezone="UTC",
    )
    await session.commit()
    return reminder.id


async def get_reminder_status(session_factory, reminder_id: int) -> tuple[str, str | None]:
    async with session_factory() as session:
        reminder = await ReminderRepository(session).get_by_id(reminder_id)
        assert reminder is not None
        return reminder.status, reminder.error_text


def test_send_reminder_job_marks_sent_after_success(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine, session_factory = await make_session_factory(tmp_path)
        try:
            now = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
            async with session_factory() as session:
                reminder_id = await create_reminder(
                    session,
                    remind_at_utc=now - timedelta(minutes=5),
                )

            bot = FakeBot()
            await send_reminder_job(
                reminder_id=reminder_id,
                bot=bot,  # type: ignore[arg-type]
                session_factory=session_factory,
                overdue=True,
                now_func=lambda: now,
            )

            assert bot.messages == [
                (
                    7001,
                    "Reminder (this was scheduled earlier):\nBuy milk",
                )
            ]
            status, error_text = await get_reminder_status(
                session_factory,
                reminder_id,
            )
            assert status == "sent"
            assert error_text is None
        finally:
            await engine.dispose()

    run(scenario())


def test_send_reminder_job_marks_failed_after_send_error(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine, session_factory = await make_session_factory(tmp_path)
        try:
            now = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
            async with session_factory() as session:
                reminder_id = await create_reminder(
                    session,
                    remind_at_utc=now - timedelta(minutes=5),
                )

            await send_reminder_job(
                reminder_id=reminder_id,
                bot=FakeBot(error=RuntimeError("telegram is unavailable")),  # type: ignore[arg-type]
                session_factory=session_factory,
                now_func=lambda: now,
            )

            status, error_text = await get_reminder_status(
                session_factory,
                reminder_id,
            )
            assert status == "failed"
            assert error_text == "telegram is unavailable"
        finally:
            await engine.dispose()

    run(scenario())


def test_reminder_scheduler_loads_overdue_and_future_reminders(tmp_path: Path) -> None:
    async def scenario() -> None:
        engine, session_factory = await make_session_factory(tmp_path)
        try:
            now = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
            async with session_factory() as session:
                overdue_id = await create_reminder(
                    session,
                    telegram_id=7002,
                    text="Overdue",
                    remind_at_utc=now - timedelta(minutes=10),
                )
                future_id = await create_reminder(
                    session,
                    telegram_id=7003,
                    text="Future",
                    remind_at_utc=now + timedelta(minutes=10),
                )

            bot = FakeBot()
            scheduler = FakeScheduler()
            reminder_scheduler = ReminderScheduler(
                bot=bot,  # type: ignore[arg-type]
                session_factory=session_factory,
                scheduler=scheduler,  # type: ignore[arg-type]
                now_func=lambda: now,
            )

            await reminder_scheduler.start()

            assert scheduler.running
            assert bot.messages == [
                (
                    7002,
                    "Reminder (this was scheduled earlier):\nOverdue",
                )
            ]
            assert len(scheduler.jobs) == 1
            assert scheduler.jobs[0]["id"] == f"reminder:{future_id}"
            assert scheduler.jobs[0]["trigger"] == "date"

            overdue_status, _ = await get_reminder_status(
                session_factory,
                overdue_id,
            )
            future_status, _ = await get_reminder_status(
                session_factory,
                future_id,
            )
            assert overdue_status == "sent"
            assert future_status == "scheduled"
        finally:
            await engine.dispose()

    run(scenario())
