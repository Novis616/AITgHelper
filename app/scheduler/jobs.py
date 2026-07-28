from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timezone

from aiogram import Bot
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.common.time import utc_now
from app.repositories import ReminderRepository, UserRepository

logger = logging.getLogger(__name__)


def ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def reminder_message_text(*, text: str, overdue: bool = False) -> str:
    prefix = "Reminder"
    if overdue:
        prefix += " (this was scheduled earlier)"
    return f"{prefix}:\n{text}"


def compact_error_text(error: Exception, *, limit: int = 1000) -> str:
    message = str(error) or error.__class__.__name__
    return message[:limit]


async def send_reminder_job(
    *,
    reminder_id: int,
    bot: Bot,
    session_factory: async_sessionmaker[AsyncSession],
    overdue: bool = False,
    now_func: Callable[[], datetime] = utc_now,
) -> None:
    async with session_factory() as session:
        reminders = ReminderRepository(session)
        users = UserRepository(session)
        reminder = await reminders.get_by_id(reminder_id)
        if reminder is None or reminder.status != "scheduled":
            return

        user = await users.get_by_id(reminder.user_id)
        if user is None:
            await reminders.mark_failed(reminder, error_text="Reminder user not found")
            await session.commit()
            logger.warning("Reminder user not found: reminder_id=%s", reminder_id)
            return

        try:
            await bot.send_message(
                chat_id=user.telegram_id,
                text=reminder_message_text(text=reminder.text, overdue=overdue),
            )
        except Exception as exc:
            await reminders.mark_failed(reminder, error_text=compact_error_text(exc))
            await session.commit()
            logger.exception("Could not send reminder: reminder_id=%s", reminder_id)
            return

        await reminders.mark_sent(reminder, sent_at=ensure_aware_utc(now_func()))
        await session.commit()
        logger.info("Reminder sent: reminder_id=%s", reminder_id)
