from sqlalchemy.ext.asyncio import AsyncSession

from app.common.errors import NotFoundError, ValidationError
from app.repositories import NoteCategoryRepository, NoteRepository, UserRepository
from app.repositories.note_category_repository import normalize_category_name
from app.schemas.note import CreateForwardedNoteInput, CreateNoteInput, NoteRead
from app.security.encryption import decrypt_text


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
        return self._to_read(note)

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
        return self._to_read(note)

    async def list_notes(self, *, telegram_id: int, limit: int = 20) -> list[NoteRead]:
        if limit <= 0:
            raise ValidationError("limit must be greater than zero")
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            return []
        notes = await self.notes.list_for_user(user.id, limit=limit)
        return [self._to_read(note) for note in notes]

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

    async def count_notes(self, *, telegram_id: int) -> int:
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            return 0
        return await self.notes.count_for_user(user.id)

    async def count_notes_by_category(
        self,
        *,
        telegram_id: int,
        category_name: str,
    ) -> int:
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            return 0
        category = await self.categories.get_by_normalized_name(
            user_id=user.id,
            normalized_name=normalize_category_name(category_name),
        )
        if category is None:
            return 0
        notes = await self.notes.list_by_category_for_user(
            user_id=user.id,
            category_id=category.id,
        )
        return len(notes)

    async def count_existing_notes_by_ids(
        self,
        *,
        telegram_id: int,
        note_ids: list[int],
    ) -> int:
        clean_ids = self._clean_note_ids(note_ids)
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            return 0
        notes = await self.notes.list_by_ids_for_user(user.id, clean_ids)
        found_ids = {note.id for note in notes}
        if found_ids != set(clean_ids):
            return 0
        return len(notes)

    async def delete_notes_by_ids(
        self,
        *,
        telegram_id: int,
        note_ids: list[int],
    ) -> int:
        clean_ids = self._clean_note_ids(note_ids)
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            raise NotFoundError("Notes not found")
        notes = await self.notes.list_by_ids_for_user(user.id, clean_ids)
        found_ids = {note.id for note in notes}
        if found_ids != set(clean_ids):
            raise NotFoundError("Notes not found")
        deleted_count = await self.notes.delete_many(notes)
        await self.session.commit()
        return deleted_count

    async def delete_notes_by_category(
        self,
        *,
        telegram_id: int,
        category_name: str,
    ) -> int:
        cleaned = self._clean_required_text(category_name, "category_name")
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            raise NotFoundError("Category notes not found")
        category = await self.categories.get_by_normalized_name(
            user_id=user.id,
            normalized_name=normalize_category_name(cleaned),
        )
        if category is None:
            raise NotFoundError("Category notes not found")
        notes = await self.notes.list_by_category_for_user(
            user_id=user.id,
            category_id=category.id,
        )
        if not notes:
            raise NotFoundError("Category notes not found")
        deleted_count = await self.notes.delete_many(notes)
        await self.session.commit()
        return deleted_count

    async def delete_all_notes(self, *, telegram_id: int) -> int:
        user = await self.users.get_by_telegram_id(telegram_id)
        if user is None:
            raise NotFoundError("Notes not found")
        notes = await self.notes.list_for_user(user.id, limit=100000)
        if not notes:
            raise NotFoundError("Notes not found")
        deleted_count = await self.notes.delete_many(notes)
        await self.session.commit()
        return deleted_count

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

    def _clean_note_ids(self, note_ids: list[int]) -> list[int]:
        clean_ids: list[int] = []
        seen: set[int] = set()
        for note_id in note_ids:
            if note_id <= 0:
                raise ValidationError("note_ids must contain positive ids")
            if note_id not in seen:
                clean_ids.append(note_id)
                seen.add(note_id)
        if not clean_ids:
            raise ValidationError("note_ids must not be empty")
        return clean_ids

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

    def _to_read(self, note) -> NoteRead:
        return NoteRead(
            id=note.id,
            user_id=note.user_id,
            category_id=note.category_id,
            category_name=note.category_name,
            title=decrypt_text(note.title),
            content=decrypt_text(note.content) or "",
            source_type=note.source_type,
            source_chat_id=note.source_chat_id,
            source_chat_title=decrypt_text(note.source_chat_title),
            source_message_id=note.source_message_id,
            forward_sender_name=decrypt_text(note.forward_sender_name),
            language=note.language,
            created_at=note.created_at,
            updated_at=note.updated_at,
        )
