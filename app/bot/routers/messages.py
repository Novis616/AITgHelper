from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot.formatters.messages import message_text, note_saved_text
from app.bot.telegram_message import (
    extract_forward_info,
    get_message_language,
    get_sender_telegram_id,
    is_forwarded_message,
)
from app.common.errors import ServiceError, ValidationError
from app.schemas import CreateForwardedNoteInput, CreateNoteInput, IncomingTextMessage
from app.services import IncomingMessageService, NoteService, ReminderSchedulingPort

logger = logging.getLogger(__name__)
router = Router(name="messages")


@router.message(F.text.startswith("/"))
async def handle_unknown_command(message: Message) -> None:
    language = get_message_language(message)
    await message.answer(message_text("unknown_command", language))


@router.message(F.text)
async def handle_text_message(
    message: Message,
    session: AsyncSession,
    reminder_scheduler: ReminderSchedulingPort | None = None,
) -> None:
    service = IncomingMessageService(
        session,
        reminder_scheduler=reminder_scheduler,
    )
    language = get_message_language(message)
    try:
        answer = await process_text_message(message, service)
    except ValidationError:
        answer = message_text("empty_text", language)
    except (ServiceError, ValueError):
        logger.exception(
            "Could not save Telegram message: message_id=%s",
            getattr(message, "message_id", None),
        )
        answer = message_text("service_error", language)

    await message.answer(answer)


async def process_text_message(message: Message, service: IncomingMessageService) -> str:
    text = (message.text or "").strip()
    source_type = "forwarded" if is_forwarded_message(message) else "plain"
    result = await service.handle_text_message(
        IncomingTextMessage(
            telegram_id=get_sender_telegram_id(message),
            text=text,
            language=get_message_language(message),
            source_type=source_type,
            forward=extract_forward_info(message) if source_type == "forwarded" else None,
        )
    )
    return result.text


async def save_text_message(message: Message, service: NoteService) -> str:
    text = (message.text or "").strip()
    language = get_message_language(message)
    telegram_id = get_sender_telegram_id(message)

    if is_forwarded_message(message):
        note = await service.create_forwarded_text_note(
            CreateForwardedNoteInput(
                telegram_id=telegram_id,
                content=text,
                language=language,
                forward=extract_forward_info(message),
            )
        )
        return note_saved_text(note, language, forwarded=True)

    note = await service.create_note(
        CreateNoteInput(
            telegram_id=telegram_id,
            content=text,
            language=language,
        )
    )
    return note_saved_text(note, language, forwarded=False)
