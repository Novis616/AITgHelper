from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.common.time import utc_now
from app.schemas import NoteRead, ReminderRead


def note_saved_text(note: NoteRead, language: str, *, forwarded: bool) -> str:
    if _is_en(language):
        if forwarded:
            return f"Done, saved the forwarded message as note #{note.id}."
        return f"Done, saved note #{note.id}."
    if forwarded:
        return f"Готово, сохранил пересланное сообщение как заметку #{note.id}."
    return f"Готово, сохранил заметку #{note.id}."


def clarification_text(question: str | None, language: str) -> str:
    if question:
        return question
    if _is_en(language):
        return (
            "I am not sure what to do. Please write: save a note, "
            "show notes, or create a reminder."
        )
    return (
        "Уточни, что нужно сделать: сохранить заметку, показать заметки "
        "или создать напоминание."
    )


def list_notes_text(notes: list[NoteRead], language: str) -> str:
    if not notes:
        return "No notes yet." if _is_en(language) else "Заметок пока нет."
    lines = ["Notes:" if _is_en(language) else "Заметки:"]
    for note in notes:
        lines.append(f"#{note.id}: {_single_line_preview(note.content)}")
    return "\n".join(lines)


def list_reminders_text(reminders: list[ReminderRead], language: str) -> str:
    if not reminders:
        return (
            "No active reminders yet."
            if _is_en(language)
            else "Активных напоминаний пока нет."
        )
    lines = ["Reminders:" if _is_en(language) else "Напоминания:"]
    for reminder in reminders:
        when = reminder.remind_at_utc.astimezone().strftime("%Y-%m-%d %H:%M")
        lines.append(f"#{reminder.id}: {when} - {_single_line_preview(reminder.text)}")
    return "\n".join(lines)


def _legacy_reminder_created_text(reminder: ReminderRead, language: str) -> str:
    when = reminder.remind_at_utc.astimezone().strftime("%Y-%m-%d %H:%M")
    if _is_en(language):
        return f"Done, created reminder #{reminder.id}: {when}."
    return f"Готово, создал напоминание #{reminder.id}: {when}."


def deleted_text(item_type: str, item_id: int, language: str) -> str:
    if item_type == "reminder":
        if _is_en(language):
            return f"Cancelled reminder #{item_id}."
        return f"Отменил напоминание #{item_id}."
    if _is_en(language):
        return f"Deleted note #{item_id}."
    return f"Удалил заметку #{item_id}."


def not_found_text(item_type: str, language: str) -> str:
    if item_type == "reminder":
        if _is_en(language):
            return "I could not find that reminder."
        return "Не нашел такое напоминание."
    if _is_en(language):
        return "I could not find that note."
    return "Не нашел такую заметку."


def reminder_cannot_cancel_text(language: str) -> str:
    if _is_en(language):
        return "That reminder cannot be cancelled anymore."
    return "Это напоминание уже нельзя отменить."


def reminder_time_invalid_text(language: str) -> str:
    if _is_en(language):
        return "I need an exact future time. Example: 2026-07-29 09:00."
    return "Нужно точное будущее время. Пример: 2026-07-29 09:00."


def _single_line_preview(value: str, *, max_length: int = 80) -> str:
    preview = " ".join(value.split())
    if len(preview) <= max_length:
        return preview
    return f"{preview[: max_length - 3]}..."


def _is_en(language: str) -> bool:
    return language.lower().split("-", maxsplit=1)[0] == "en"


class _ReminderTimeModule:
    def __init__(self, *, ru: str, en: str) -> None:
        self.ru = ru
        self.en = en


def reminder_created_text(
    reminder: ReminderRead,
    language: str,
    *,
    now: datetime | None = None,
) -> str:
    when = _reminder_time_module(reminder, now=now)
    if _is_en(language):
        return f"Done, created reminder {when.en}."
    return f"Готово, создал напоминание {when.ru}."


def _reminder_time_module(
    reminder: ReminderRead,
    *,
    now: datetime | None = None,
) -> _ReminderTimeModule:
    timezone_info = _safe_zoneinfo(reminder.timezone)
    remind_at = _ensure_aware_utc(reminder.remind_at_utc).astimezone(timezone_info)
    current = _ensure_aware_utc(now or utc_now()).astimezone(timezone_info)

    time_part = remind_at.strftime("%H:%M")
    if remind_at.date() == current.date():
        return _ReminderTimeModule(ru=f"на {time_part}", en=f"at {time_part}")

    if remind_at.year == current.year:
        date_part = remind_at.strftime("%d.%m")
        return _ReminderTimeModule(
            ru=f"на {date_part} в {time_part}",
            en=f"on {date_part} at {time_part}",
        )

    date_part = remind_at.strftime("%d.%m.%Y")
    return _ReminderTimeModule(
        ru=f"на {date_part} в {time_part}",
        en=f"on {date_part} at {time_part}",
    )


def _safe_zoneinfo(timezone_name: str) -> ZoneInfo | timezone:
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        return timezone.utc


def _ensure_aware_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
