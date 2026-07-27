from sqlalchemy import Select, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.note import Note


class NoteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        user_id: int,
        content: str,
        title: str | None = None,
        source_type: str = "plain",
        source_chat_id: int | None = None,
        source_chat_title: str | None = None,
        source_message_id: int | None = None,
        forward_sender_name: str | None = None,
        language: str = "ru",
    ) -> Note:
        note = Note(
            user_id=user_id,
            title=title,
            content=content,
            source_type=source_type,
            source_chat_id=source_chat_id,
            source_chat_title=source_chat_title,
            source_message_id=source_message_id,
            forward_sender_name=forward_sender_name,
            language=language,
        )
        self.session.add(note)
        await self.session.flush()
        return note

    async def get_by_id(self, note_id: int) -> Note | None:
        return await self.session.get(Note, note_id)

    async def list_for_user(self, user_id: int, *, limit: int = 20) -> list[Note]:
        stmt: Select[tuple[Note]] = (
            select(Note)
            .where(Note.user_id == user_id)
            .order_by(desc(Note.created_at), desc(Note.id))
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete(self, note: Note) -> None:
        await self.session.delete(note)
        await self.session.flush()
