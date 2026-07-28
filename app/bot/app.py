from __future__ import annotations

import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bot.middlewares.access import AccessControlMiddleware
from app.bot.middlewares.db_session import DbSessionMiddleware
from app.bot.routers import common, messages
from app.config.settings import Settings, get_settings
from app.repositories.database import async_session_factory, engine

logger = logging.getLogger(__name__)


def create_dispatcher(
    *,
    settings: Settings | None = None,
    session_factory: async_sessionmaker[AsyncSession] = async_session_factory,
) -> Dispatcher:
    settings = settings or get_settings()
    dispatcher = Dispatcher()
    dispatcher.message.middleware(DbSessionMiddleware(session_factory))
    dispatcher.message.middleware(AccessControlMiddleware(settings))
    dispatcher.include_router(common.router)
    dispatcher.include_router(messages.router)
    return dispatcher


async def run_bot(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to start the bot")

    dispatcher = create_dispatcher(settings=settings)
    bot = Bot(
        token=settings.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=None),
    )
    logger.info("Starting Telegram bot polling")
    try:
        await dispatcher.start_polling(
            bot,
            allowed_updates=dispatcher.resolve_used_update_types(),
        )
    finally:
        await bot.session.close()
        await engine.dispose()
