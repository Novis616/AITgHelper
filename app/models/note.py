from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.note_category import NoteCategory
    from app.models.user import User


class Note(TimestampMixin, Base):
    __tablename__ = "notes"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("note_categories.id"),
        index=True,
    )
    title: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_type: Mapped[str] = mapped_column(
        String(32),
        default="plain",
        nullable=False,
        index=True,
    )
    source_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    source_chat_title: Mapped[str | None] = mapped_column(String(255))
    source_message_id: Mapped[int | None] = mapped_column(BigInteger)
    forward_sender_name: Mapped[str | None] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(8), default="ru", nullable=False)

    user: Mapped["User"] = relationship(back_populates="notes")
    category: Mapped["NoteCategory | None"] = relationship(back_populates="notes")

    @property
    def category_name(self) -> str | None:
        if self.category is None:
            return None
        return self.category.name
