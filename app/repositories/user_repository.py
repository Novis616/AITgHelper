from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        telegram_id: int,
        language: str = "ru",
        timezone: str = "Europe/Moscow",
    ) -> User:
        user = User(telegram_id=telegram_id, language=language, timezone=timezone)
        self.session.add(user)
        await self.session.flush()
        return user

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self.session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        *,
        telegram_id: int,
        language: str = "ru",
        timezone: str = "Europe/Moscow",
    ) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if user is not None:
            return user
        return await self.create(
            telegram_id=telegram_id,
            language=language,
            timezone=timezone,
        )

    async def update_preferences(
        self,
        user: User,
        *,
        language: str | None = None,
        timezone: str | None = None,
    ) -> User:
        if language is not None:
            user.language = language
        if timezone is not None:
            user.timezone = timezone
        await self.session.flush()
        return user
