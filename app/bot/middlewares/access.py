from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from app.bot.formatters.messages import message_text
from app.bot.telegram_message import get_message_language
from app.config.settings import Settings


class AccessControlMiddleware(BaseMiddleware):
    def __init__(self, settings: Settings) -> None:
        self.allowed_user_ids = set(settings.allowed_telegram_user_ids)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not self.allowed_user_ids or not isinstance(event, Message):
            return await handler(event, data)

        from_user = event.from_user
        if from_user is not None and from_user.id in self.allowed_user_ids:
            return await handler(event, data)

        language = get_message_language(event)
        await event.answer(message_text("not_allowed", language))
        return None
