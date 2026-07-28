from app.schemas import NoteRead


SUPPORTED_LANGUAGES = {"ru", "en"}

MESSAGES: dict[str, dict[str, str]] = {
    "ru": {
        "thinking": "Thinking...",
        "start": (
            "Привет! Я AITgHelper.\n\n"
            "Что я умею:\n"
            "- сохранять обычные и пересланные сообщения как заметки;\n"
            "- раскладывать заметки по категориям, например: "
            "\"сохрани в закладку Покупки\";\n"
            "- показывать и удалять заметки;\n"
            "- удалять несколько заметок, категорию заметок или все заметки "
            "после подтверждения;\n"
            "- создавать напоминания из обычных и пересланных сообщений, например: "
            "\"напомни через час открыть дверь\";\n"
            "- показывать и отменять напоминания;\n"
            "- массово отменять напоминания после подтверждения.\n\n"
            "Примеры:\n"
            "https://ozon.ru/... сохрани в закладку Покупки\n"
            "покажи заметки\n"
            "напомни через 2 минуты закрыть дверь\n"
            "удали заметки 1, 3, 7\n"
            "удали все напоминания"
        ),
        "help": (
            "/start - показать возможности бота\n"
            "/help - показать помощь\n\n"
            "Пиши обычным текстом: я сам определю, нужна заметка, категория "
            "или напоминание. Для массового удаления я всегда сначала спрошу: "
            "Удаляем? Да/Нет."
        ),
        "note_saved": "Готово, сохранил заметку #{note_id}.",
        "forwarded_note_saved": (
            "Готово, сохранил пересланное сообщение как заметку #{note_id}."
        ),
        "empty_text": (
            "Пришли текстовое сообщение, чтобы я сохранил его как заметку."
        ),
        "not_allowed": (
            "У этого Telegram-аккаунта пока нет доступа к боту."
        ),
        "unknown_command": "Я пока знаю только /start и /help.",
        "service_error": (
            "Не получилось обработать сообщение. Попробуй еще раз."
        ),
    },
    "en": {
        "thinking": "Thinking...",
        "start": (
            "Hi! I am AITgHelper.\n\n"
            "What I can do:\n"
            "- save regular and forwarded messages as notes;\n"
            "- organize notes into categories, for example: "
            "\"save to Shopping\";\n"
            "- show and delete notes;\n"
            "- delete several notes, a note category, or all notes after "
            "confirmation;\n"
            "- create reminders from regular and forwarded messages, for example: "
            "\"remind me in 1 hour to open the door\";\n"
            "- show and cancel reminders;\n"
            "- cancel several reminders or all reminders after confirmation.\n\n"
            "Examples:\n"
            "https://ozon.ru/... save to Shopping\n"
            "show notes\n"
            "remind me in 2 minutes to close the door\n"
            "delete notes 1, 3, 7\n"
            "delete all reminders"
        ),
        "help": (
            "/start - show bot features\n"
            "/help - show help\n\n"
            "Write naturally: I will decide whether you need a note, category, "
            "or reminder. For bulk deletion I always ask for confirmation first: "
            "Delete? Yes/No."
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
