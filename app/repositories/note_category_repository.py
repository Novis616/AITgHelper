import re

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note_category import NoteCategory


class NoteCategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: int,
        name: str,
    ) -> NoteCategory:
        normalized_name = normalize_category_name(name)
        category = NoteCategory(
            user_id=user_id,
            name=clean_category_name(name),
            normalized_name=normalized_name,
        )
        self.session.add(category)
        await self.session.flush()
        return category

    async def get_by_normalized_name(
        self,
        *,
        user_id: int,
        normalized_name: str,
    ) -> NoteCategory | None:
        stmt: Select[tuple[NoteCategory]] = (
            select(NoteCategory)
            .where(NoteCategory.user_id == user_id)
            .where(NoteCategory.normalized_name == normalized_name)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        *,
        user_id: int,
        name: str,
    ) -> NoteCategory:
        normalized_name = normalize_category_name(name)
        category = await self.get_by_normalized_name(
            user_id=user_id,
            normalized_name=normalized_name,
        )
        if category is not None:
            return category
        return await self.create(user_id=user_id, name=name)

    async def list_for_user(self, user_id: int) -> list[NoteCategory]:
        stmt: Select[tuple[NoteCategory]] = (
            select(NoteCategory)
            .where(NoteCategory.user_id == user_id)
            .order_by(NoteCategory.name, NoteCategory.id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


def clean_category_name(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def normalize_category_name(value: str) -> str:
    return clean_category_name(value).casefold()
