from datetime import datetime

from sqlalchemy import Select, asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import utc_now
from app.models.reminder import Reminder


class ReminderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: int,
        text: str,
        remind_at_utc: datetime,
        timezone: str,
        status: str = "scheduled",
    ) -> Reminder:
        reminder = Reminder(
            user_id=user_id,
            text=text,
            remind_at_utc=remind_at_utc,
            timezone=timezone,
            status=status,
            created_at=utc_now(),
        )
        self.session.add(reminder)
        await self.session.flush()
        return reminder

    async def get_by_id(self, reminder_id: int) -> Reminder | None:
        return await self.session.get(Reminder, reminder_id)

    async def list_for_user(
        self,
        user_id: int,
        *,
        status: str | None = None,
        limit: int = 20,
    ) -> list[Reminder]:
        stmt: Select[tuple[Reminder]] = select(Reminder).where(
            Reminder.user_id == user_id
        )
        if status is not None:
            stmt = stmt.where(Reminder.status == status)
        stmt = stmt.order_by(desc(Reminder.remind_at_utc), desc(Reminder.id)).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_scheduled_due_before(self, when_utc: datetime) -> list[Reminder]:
        stmt = (
            select(Reminder)
            .where(Reminder.status == "scheduled")
            .where(Reminder.remind_at_utc <= when_utc)
            .order_by(asc(Reminder.remind_at_utc), asc(Reminder.id))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_future_scheduled_after(self, when_utc: datetime) -> list[Reminder]:
        stmt = (
            select(Reminder)
            .where(Reminder.status == "scheduled")
            .where(Reminder.remind_at_utc > when_utc)
            .order_by(asc(Reminder.remind_at_utc), asc(Reminder.id))
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_sent(
        self,
        reminder: Reminder,
        *,
        sent_at: datetime | None = None,
    ) -> Reminder:
        reminder.status = "sent"
        reminder.sent_at = sent_at or utc_now()
        reminder.error_text = None
        await self.session.flush()
        return reminder

    async def mark_failed(self, reminder: Reminder, *, error_text: str) -> Reminder:
        reminder.status = "failed"
        reminder.error_text = error_text
        await self.session.flush()
        return reminder

    async def cancel(self, reminder: Reminder) -> Reminder:
        reminder.status = "cancelled"
        await self.session.flush()
        return reminder
