from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.common.time import utc_now
from app.repositories import ReminderRepository
from app.scheduler.jobs import ensure_aware_utc, send_reminder_job

logger = logging.getLogger(__name__)


def create_apscheduler() -> AsyncIOScheduler:
    return AsyncIOScheduler(timezone=timezone.utc)


class ReminderScheduler:
    def __init__(
        self,
        *,
        bot: Bot,
        session_factory: async_sessionmaker[AsyncSession],
        scheduler: AsyncIOScheduler | None = None,
        now_func: Callable[[], datetime] = utc_now,
    ) -> None:
        self.bot = bot
        self.session_factory = session_factory
        self.scheduler = scheduler or create_apscheduler()
        self.now_func = now_func

    async def start(self) -> None:
        if not self.scheduler.running:
            self.scheduler.start()
        await self.load_scheduled_reminders()

    async def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    async def load_scheduled_reminders(self) -> None:
        now = ensure_aware_utc(self.now_func())
        async with self.session_factory() as session:
            reminders = ReminderRepository(session)
            overdue = await reminders.list_scheduled_due_before(now)
            future = await reminders.list_future_scheduled_after(now)

        for reminder in overdue:
            await send_reminder_job(
                reminder_id=reminder.id,
                bot=self.bot,
                session_factory=self.session_factory,
                overdue=True,
                now_func=self.now_func,
            )

        for reminder in future:
            self.schedule_reminder(reminder.id, reminder.remind_at_utc)

        logger.info(
            "Reminder scheduler loaded reminders: overdue=%s future=%s",
            len(overdue),
            len(future),
        )

    def schedule_reminder(self, reminder_id: int, remind_at_utc: datetime) -> None:
        self.scheduler.add_job(
            send_reminder_job,
            trigger="date",
            run_date=ensure_aware_utc(remind_at_utc),
            id=self.job_id(reminder_id),
            replace_existing=True,
            kwargs={
                "reminder_id": reminder_id,
                "bot": self.bot,
                "session_factory": self.session_factory,
                "now_func": self.now_func,
            },
        )

    @staticmethod
    def job_id(reminder_id: int) -> str:
        return f"reminder:{reminder_id}"
