from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from app.bot.formatters.messages import message_text
from app.bot.telegram_message import get_message_language

router = Router(name="common")


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    language = get_message_language(message)
    await message.answer(message_text("start", language))


@router.message(Command("help"))
async def handle_help(message: Message) -> None:
    language = get_message_language(message)
    await message.answer(message_text("help", language))
