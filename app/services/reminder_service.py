from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import NotFoundError, ValidationError
from app.common.time import to_utc, utc_now
from app.config.settings import Settings, get_settings
from app.repositories import ReminderRepository, UserRepository
from app.schemas.reminder import CreateReminderInput, ReminderRead


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
        return ReminderRead.model_validate(reminder)

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
        return [ReminderRead.model_validate(reminder) for reminder in reminders]

    async def cancel_reminder(self, *, telegram_id: int, reminder_id: int) -> ReminderRead:
        user = await self.users.get_by_telegram_id(telegram_id)
        reminder = await self.reminders.get_by_id(reminder_id)
        if user is None or reminder is None or reminder.user_id != user.id:
            raise NotFoundError("Reminder not found")
        if reminder.status != "scheduled":
            raise ValidationError("Only scheduled reminders can be cancelled")

        reminder = await self.reminders.cancel(reminder)
        await self.session.commit()
        return ReminderRead.model_validate(reminder)
