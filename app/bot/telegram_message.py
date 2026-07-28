from __future__ import annotations

from typing import Any

from app.bot.formatters.messages import normalize_language
from app.schemas import ForwardInfo


def get_message_language(message: Any) -> str:
    from_user = getattr(message, "from_user", None)
    return normalize_language(getattr(from_user, "language_code", None))


def get_sender_telegram_id(message: Any) -> int:
    from_user = getattr(message, "from_user", None)
    telegram_id = getattr(from_user, "id", None)
    if telegram_id is None:
        raise ValueError("Telegram message has no sender user id")
    return int(telegram_id)


def is_forwarded_message(message: Any) -> bool:
    if getattr(message, "forward_origin", None) is not None:
        return True

    old_forward_fields = (
        "forward_from",
        "forward_from_chat",
        "forward_sender_name",
        "forward_date",
    )
    return any(getattr(message, field, None) is not None for field in old_forward_fields)


def extract_forward_info(message: Any) -> ForwardInfo:
    origin = getattr(message, "forward_origin", None)
    if origin is not None:
        return _extract_forward_origin_info(origin)

    source_chat = getattr(message, "forward_from_chat", None)
    forward_from = getattr(message, "forward_from", None)
    return ForwardInfo(
        source_chat_id=getattr(source_chat, "id", None),
        source_chat_title=getattr(source_chat, "title", None),
        source_message_id=getattr(message, "forward_from_message_id", None),
        forward_sender_name=(
            getattr(message, "forward_sender_name", None)
            or _format_user_name(forward_from)
        ),
    )


def _extract_forward_origin_info(origin: Any) -> ForwardInfo:
    chat = getattr(origin, "chat", None) or getattr(origin, "sender_chat", None)
    sender_user = getattr(origin, "sender_user", None)
    return ForwardInfo(
        source_chat_id=getattr(chat, "id", None),
        source_chat_title=getattr(chat, "title", None),
        source_message_id=getattr(origin, "message_id", None),
        forward_sender_name=(
            getattr(origin, "sender_user_name", None)
            or getattr(origin, "author_signature", None)
            or _format_user_name(sender_user)
        ),
    )


def _format_user_name(user: Any) -> str | None:
    if user is None:
        return None
    full_name = getattr(user, "full_name", None)
    if full_name:
        return str(full_name)

    first_name = getattr(user, "first_name", None)
    last_name = getattr(user, "last_name", None)
    name = " ".join(part for part in (first_name, last_name) if part)
    return name or None
