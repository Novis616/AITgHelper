from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import NotFoundError, ValidationError
from app.repositories import NoteCategoryRepository, NoteRepository, UserRepository
from app.schemas.note import CreateForwardedNoteInput, CreateNoteInput, NoteRead


class NoteService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.notes = NoteRepository(session)
        self.categories = NoteCategoryRepository(session)

    async def create_note(self, data: CreateNoteInput) -> NoteRead:
        content = self._clean_required_text(data.content, "content")
        title = self._clean_optional_text(data.title)
        user = await self.users.get_or_create(
            telegram_id=data.telegram_id,
            language=data.language,
        )
        category = await self._get_or_create_category(
            user_id=user.id,
            name=data.category_name,
        )
        note = await self.notes.create(
            user_id=user.id,
            title=title,
            content=content,
            category=category,
            source_type="plain",
            language=data.language,
        )
        await self.session.commit()
        return NoteRead.model_validate(note)

    async def create_forwarded_text_note(
        self,
        data: CreateForwardedNoteInput,
    ) -> NoteRead:
        content = self._clean_required_text(data.content, "content")
        title = self._clean_optional_text(data.title)
        user = await self.users.get_or_create(
            telegram_id=data.telegram_id,
            language=data.language,
        )
        category = await self._get_or_create_category(
            user_id=user.id,
            name=data.category_name,
        )
        note = await self.notes.create(
            user_id=user.id,
            title=title,
            content=content,
            category=category,
            source_type="forwarded",
            source_chat_id=data.forward.source_chat_id,
            source_chat_title=data.forward.source_chat_title,
            source_message_id=data.forward.source_message_id,
            forward_sender_name=data.forward.forward_sender_name,
            language=data.language,
        )
        await self.session.commit()
        return NoteRead.model_validate(note)

    async def list_notes(self, *, telegram_id: int, limit: int = 20) -> list[NoteRead]:
        if limit <= 0:
            raise ValidationError("limit must be greater than zero")
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            return []
        notes = await self.notes.list_for_user(user.id, limit=limit)
        return [NoteRead.model_validate(note) for note in notes]

    async def list_category_names(self, *, telegram_id: int) -> list[str]:
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            return []
        categories = await self.categories.list_for_user(user.id)
        return [category.name for category in categories]

    async def delete_note(self, *, telegram_id: int, note_id: int) -> None:
        user = await self.users.get_by_telegram_id(telegram_id)
        note = await self.notes.get_by_id(note_id)
        if user is None or note is None or note.user_id != user.id:
            raise NotFoundError("Note not found")
        await self.notes.delete(note)
        await self.session.commit()

    def _clean_required_text(self, value: str, field_name: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValidationError(f"{field_name} must not be empty")
        return cleaned

    def _clean_optional_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    async def _get_or_create_category(
        self,
        *,
        user_id: int,
        name: str | None,
    ):
        cleaned = self._clean_optional_text(name)
        if cleaned is None:
            return None
        return await self.categories.get_or_create(user_id=user_id, name=cleaned)
