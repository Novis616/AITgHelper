from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import NotFoundError, ValidationError
from app.common.time import to_utc, utc_now
from app.config.settings import Settings, get_settings
from app.repositories import ReminderRepository, UserRepository
from app.schemas.reminder import CreateReminderInput, ReminderRead
from app.security.encryption import decrypt_text


class ReminderService:
    def __init__(
        self,
        session: AsyncSession,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.users = UserRepository(session)
        self.reminders = ReminderRepository(session)

    async def create_reminder(self, data: CreateReminderInput) -> ReminderRead:
        text = data.text.strip()
        if not text:
            raise ValidationError("text must not be empty")

        initial_timezone = data.timezone or self.settings.default_timezone
        user = await self.users.get_or_create(
            telegram_id=data.telegram_id,
            language=data.language,
            timezone=initial_timezone,
        )
        timezone_name = data.timezone or user.timezone or self.settings.default_timezone
        remind_at_utc = to_utc(data.remind_at, timezone_name)
        if remind_at_utc <= utc_now():
            raise ValidationError("remind_at must be in the future")

        reminder = await self.reminders.create(
            user_id=user.id,
            text=text,
            remind_at_utc=remind_at_utc,
            timezone=timezone_name,
            status="scheduled",
        )
        await self.session.commit()
        return self._to_read(reminder)

    async def list_reminders(
        self,
        *,
        telegram_id: int,
        status: str | None = None,
        limit: int = 20,
    ) -> list[ReminderRead]:
        if limit <= 0:
            raise ValidationError("limit must be greater than zero")
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            return []
        reminders = await self.reminders.list_for_user(
            user.id,
            status=status,
            limit=limit,
        )
        return [self._to_read(reminder) for reminder in reminders]

    async def cancel_reminder(self, *, telegram_id: int, reminder_id: int) -> ReminderRead:
        user = await self.users.get_by_telegram_id(telegram_id)
        reminder = await self.reminders.get_by_id(reminder_id)
        if user is None or reminder is None or reminder.user_id != user.id:
            raise NotFoundError("Reminder not found")
        if reminder.status != "scheduled":
            raise ValidationError("Only scheduled reminders can be cancelled")

        reminder = await self.reminders.cancel(reminder)
        await self.session.commit()
        return self._to_read(reminder)

    async def count_scheduled_reminders(self, *, telegram_id: int) -> int:
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            return 0
        return await self.reminders.count_scheduled_for_user(user.id)

    async def count_existing_scheduled_reminders_by_ids(
        self,
        *,
        telegram_id: int,
        reminder_ids: list[int],
    ) -> int:
        clean_ids = self._clean_reminder_ids(reminder_ids)
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            return 0
        reminders = await self.reminders.list_scheduled_by_ids_for_user(
            user.id,
            clean_ids,
        )
        found_ids = {reminder.id for reminder in reminders}
        if found_ids != set(clean_ids):
            return 0
        return len(reminders)

    async def cancel_reminders_by_ids(
        self,
        *,
        telegram_id: int,
        reminder_ids: list[int],
    ) -> int:
        clean_ids = self._clean_reminder_ids(reminder_ids)
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            raise NotFoundError("Reminders not found")
        reminders = await self.reminders.list_scheduled_by_ids_for_user(
            user.id,
            clean_ids,
        )
        found_ids = {reminder.id for reminder in reminders}
        if found_ids != set(clean_ids):
            raise NotFoundError("Reminders not found")
        cancelled_count = await self.reminders.cancel_many(reminders)
        await self.session.commit()
        return cancelled_count

    async def cancel_all_scheduled_reminders(self, *, telegram_id: int) -> int:
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            raise NotFoundError("Reminders not found")
        reminders = await self.reminders.list_scheduled_for_user(user.id)
        if not reminders:
            raise NotFoundError("Reminders not found")
        cancelled_count = await self.reminders.cancel_many(reminders)
        await self.session.commit()
        return cancelled_count

    def _clean_reminder_ids(self, reminder_ids: list[int]) -> list[int]:
        clean_ids: list[int] = []
        seen: set[int] = set()
        for reminder_id in reminder_ids:
            if reminder_id <= 0:
                raise ValidationError("reminder_ids must contain positive ids")
            if reminder_id not in seen:
                clean_ids.append(reminder_id)
                seen.add(reminder_id)
        if not clean_ids:
            raise ValidationError("reminder_ids must not be empty")
        return clean_ids

    def _to_read(self, reminder) -> ReminderRead:
        return ReminderRead(
            id=reminder.id,
            user_id=reminder.user_id,
            text=decrypt_text(reminder.text) or "",
            remind_at_utc=reminder.remind_at_utc,
            timezone=reminder.timezone,
            status=reminder.status,
            created_at=reminder.created_at,
            sent_at=reminder.sent_at,
            error_text=decrypt_text(reminder.error_text),
        )
