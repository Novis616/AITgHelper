"""Initial database schema.

Revision ID: 202607270001
Revises:
Create Date: 2026-07-27
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607270001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("telegram_id", name=op.f("uq_users_telegram_id")),
    )
    op.create_index(op.f("ix_users_telegram_id"), "users", ["telegram_id"])

    op.create_table(
        "ai_request_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("user_text", sa.Text(), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("raw_response", sa.Text(), nullable=True),
        sa.Column("normalized_intent", sa.String(length=64), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_ai_request_logs_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_request_logs")),
    )
    op.create_index(
        op.f("ix_ai_request_logs_normalized_intent"),
        "ai_request_logs",
        ["normalized_intent"],
    )
    op.create_index(op.f("ix_ai_request_logs_user_id"), "ai_request_logs", ["user_id"])

    op.create_table(
        "dialog_states",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("state_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_dialog_states_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_dialog_states")),
    )
    op.create_index(op.f("ix_dialog_states_expires_at"), "dialog_states", ["expires_at"])
    op.create_index(op.f("ix_dialog_states_state_type"), "dialog_states", ["state_type"])
    op.create_index(op.f("ix_dialog_states_status"), "dialog_states", ["status"])
    op.create_index(op.f("ix_dialog_states_user_id"), "dialog_states", ["user_id"])

    op.create_table(
        "notes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_type", sa.String(length=32), nullable=False),
        sa.Column("source_chat_id", sa.BigInteger(), nullable=True),
        sa.Column("source_chat_title", sa.String(length=255), nullable=True),
        sa.Column("source_message_id", sa.BigInteger(), nullable=True),
        sa.Column("forward_sender_name", sa.String(length=255), nullable=True),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_notes_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_notes")),
    )
    op.create_index(op.f("ix_notes_source_type"), "notes", ["source_type"])
    op.create_index(op.f("ix_notes_user_id"), "notes", ["user_id"])

    op.create_table(
        "reminders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("remind_at_utc", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_text", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_reminders_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reminders")),
    )
    op.create_index(op.f("ix_reminders_remind_at_utc"), "reminders", ["remind_at_utc"])
    op.create_index(op.f("ix_reminders_status"), "reminders", ["status"])
    op.create_index(op.f("ix_reminders_user_id"), "reminders", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_reminders_user_id"), table_name="reminders")
    op.drop_index(op.f("ix_reminders_status"), table_name="reminders")
    op.drop_index(op.f("ix_reminders_remind_at_utc"), table_name="reminders")
    op.drop_table("reminders")

    op.drop_index(op.f("ix_notes_user_id"), table_name="notes")
    op.drop_index(op.f("ix_notes_source_type"), table_name="notes")
    op.drop_table("notes")

    op.drop_index(op.f("ix_dialog_states_user_id"), table_name="dialog_states")
    op.drop_index(op.f("ix_dialog_states_status"), table_name="dialog_states")
    op.drop_index(op.f("ix_dialog_states_state_type"), table_name="dialog_states")
    op.drop_index(op.f("ix_dialog_states_expires_at"), table_name="dialog_states")
    op.drop_table("dialog_states")

    op.drop_index(op.f("ix_ai_request_logs_user_id"), table_name="ai_request_logs")
    op.drop_index(
        op.f("ix_ai_request_logs_normalized_intent"),
        table_name="ai_request_logs",
    )
    op.drop_table("ai_request_logs")

    op.drop_index(op.f("ix_users_telegram_id"), table_name="users")
    op.drop_table("users")
