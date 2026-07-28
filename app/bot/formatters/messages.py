from app.schemas import NoteRead


SUPPORTED_LANGUAGES = {"ru", "en"}

MESSAGES: dict[str, dict[str, str]] = {
    "ru": {
        "start": (
            "Привет! Я AITgHelper. Пришли мне текст или перешли сообщение, "
            "и я сохраню его как заметку."
        ),
        "help": (
            "Доступные команды:\n"
            "/start - начать работу\n"
            "/help - показать помощь\n\n"
            "Пока AI еще не подключен, любой обычный или пересланный текст "
            "сохраняется как заметка."
        ),
        "note_saved": "Готово, сохранил заметку #{note_id}.",
        "forwarded_note_saved": "Готово, сохранил пересланное сообщение как заметку #{note_id}.",
        "empty_text": "Пришли текстовое сообщение, чтобы я сохранил его как заметку.",
        "not_allowed": "У этого Telegram-аккаунта пока нет доступа к боту.",
        "unknown_command": "Я пока знаю только /start и /help.",
        "service_error": "Не получилось сохранить заметку. Попробуй еще раз.",
    },
    "en": {
        "start": (
            "Hi! I am AITgHelper. Send me text or forward a message, "
            "and I will save it as a note."
        ),
        "help": (
            "Available commands:\n"
            "/start - start the bot\n"
            "/help - show help\n\n"
            "Until AI is connected, any regular or forwarded text is saved "
            "as a note."
        ),
        "note_saved": "Done, saved note #{note_id}.",
        "forwarded_note_saved": "Done, saved the forwarded message as note #{note_id}.",
        "empty_text": "Send a text message and I will save it as a note.",
        "not_allowed": "This Telegram account does not have access to the bot yet.",
        "unknown_command": "For now I only know /start and /help.",
        "service_error": "Could not save the note. Please try again.",
    },
}


def normalize_language(language_code: str | None) -> str:
    if not language_code:
        return "ru"
    language = language_code.lower().split("-", maxsplit=1)[0].split("_", maxsplit=1)[0]
    if language in SUPPORTED_LANGUAGES:
        return language
    return "ru"


def message_text(key: str, language: str, **kwargs: object) -> str:
    messages = MESSAGES.get(normalize_language(language), MESSAGES["ru"])
    return messages[key].format(**kwargs)


def note_saved_text(note: NoteRead, language: str, *, forwarded: bool) -> str:
    key = "forwarded_note_saved" if forwarded else "note_saved"
    return message_text(key, language, note_id=note.id)
