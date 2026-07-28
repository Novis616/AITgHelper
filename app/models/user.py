from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.ai_request_log import AiRequestLog
    from app.models.dialog_state import DialogState
    from app.models.note import Note
    from app.models.note_category import NoteCategory
    from app.models.reminder import Reminder


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    language: Mapped[str] = mapped_column(String(8), default="ru", nullable=False)
    timezone: Mapped[str] = mapped_column(
        String(64),
        default="Europe/Moscow",
        nullable=False,
    )

    notes: Mapped[list["Note"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    note_categories: Mapped[list["NoteCategory"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    reminders: Mapped[list["Reminder"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    dialog_states: Mapped[list["DialogState"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
    ai_request_logs: Mapped[list["AiRequestLog"]] = relationship(back_populates="user")
