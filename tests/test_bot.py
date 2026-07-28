from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from app.bot.app import create_dispatcher
from app.bot.formatters import message_text, normalize_language
from app.bot.routers.messages import save_text_message
from app.bot.telegram_message import extract_forward_info, is_forwarded_message
from app.config.settings import Settings
from app.schemas import CreateForwardedNoteInput, CreateNoteInput, NoteRead


def run(coro):
    return asyncio.run(coro)


class FakeNoteService:
    def __init__(self) -> None:
        self.plain_inputs: list[CreateNoteInput] = []
        self.forwarded_inputs: list[CreateForwardedNoteInput] = []

    async def create_note(self, data: CreateNoteInput) -> NoteRead:
        self.plain_inputs.append(data)
        return make_note(note_id=1, source_type="plain", language=data.language)

    async def create_forwarded_text_note(
        self,
        data: CreateForwardedNoteInput,
    ) -> NoteRead:
        self.forwarded_inputs.append(data)
        return make_note(note_id=2, source_type="forwarded", language=data.language)


def make_note(*, note_id: int, source_type: str, language: str) -> NoteRead:
    now = datetime.now(timezone.utc)
    return NoteRead(
        id=note_id,
        user_id=10,
        title=None,
        content="Saved text",
        source_type=source_type,
        source_chat_id=None,
        source_chat_title=None,
        source_message_id=None,
        forward_sender_name=None,
        language=language,
        created_at=now,
        updated_at=now,
    )


def make_message(**kwargs):
    defaults = {
        "text": "Remember this",
        "message_id": 123,
        "from_user": SimpleNamespace(id=42, language_code="en"),
        "forward_origin": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_normalize_language_supports_ru_and_en_with_ru_fallback() -> None:
    assert normalize_language("en-US") == "en"
    assert normalize_language("ru") == "ru"
    assert normalize_language("de") == "ru"
    assert message_text("unknown_command", "en") == "For now I only know /start and /help."


def test_extract_forward_info_from_modern_channel_origin() -> None:
    message = make_message(
        forward_origin=SimpleNamespace(
            chat=SimpleNamespace(id=-1001, title="Announcements"),
            message_id=77,
            author_signature="Editor",
        )
    )

    forward = extract_forward_info(message)

    assert is_forwarded_message(message)
    assert forward.source_chat_id == -1001
    assert forward.source_chat_title == "Announcements"
    assert forward.source_message_id == 77
    assert forward.forward_sender_name == "Editor"


def test_save_text_message_creates_plain_note_dto() -> None:
    async def scenario() -> None:
        service = FakeNoteService()
        answer = await save_text_message(make_message(), service)  # type: ignore[arg-type]

        assert answer == "Done, saved note #1."
        assert len(service.plain_inputs) == 1
        assert service.plain_inputs[0].telegram_id == 42
        assert service.plain_inputs[0].content == "Remember this"
        assert service.plain_inputs[0].language == "en"
        assert service.forwarded_inputs == []

    run(scenario())


def test_save_text_message_creates_forwarded_note_dto() -> None:
    async def scenario() -> None:
        service = FakeNoteService()
        message = make_message(
            text="Forwarded idea",
            from_user=SimpleNamespace(id=43, language_code="ru"),
            forward_origin=SimpleNamespace(
                sender_user=SimpleNamespace(full_name="Alice"),
            ),
        )

        answer = await save_text_message(message, service)  # type: ignore[arg-type]

        assert answer == "Готово, сохранил пересланное сообщение как заметку #2."
        assert len(service.forwarded_inputs) == 1
        forwarded = service.forwarded_inputs[0]
        assert forwarded.telegram_id == 43
        assert forwarded.content == "Forwarded idea"
        assert forwarded.language == "ru"
        assert forwarded.forward.forward_sender_name == "Alice"
        assert service.plain_inputs == []

    run(scenario())


def test_create_dispatcher_registers_bot_stack() -> None:
    dispatcher = create_dispatcher(settings=Settings(telegram_bot_token="test-token"))

    assert dispatcher.resolve_used_update_types() == ["message"]
