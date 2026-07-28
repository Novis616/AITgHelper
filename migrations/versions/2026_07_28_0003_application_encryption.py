"""Encrypt sensitive application data.

Revision ID: 202607280003
Revises: 202607280002
Create Date: 2026-07-28
"""

from __future__ import annotations

from collections.abc import Sequence
import json
from typing import Any

from alembic import op
import sqlalchemy as sa

from app.security.encryption import (
    decrypt_json,
    decrypt_text,
    encrypt_json,
    encrypt_text,
    is_encrypted,
)

revision: str = "202607280003"
down_revision: str | None = "202607280002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("dialog_states") as batch_op:
        batch_op.alter_column(
            "payload",
            existing_type=sa.JSON(),
            type_=sa.Text(),
            existing_nullable=False,
        )

    _encrypt_text_columns(
        table="notes",
        columns=("title", "content", "source_chat_title", "forward_sender_name"),
    )
    _encrypt_text_columns(table="reminders", columns=("text", "error_text"))
    _encrypt_text_columns(
        table="ai_request_logs",
        columns=("user_text", "prompt", "raw_response", "error_text"),
    )
    _encrypt_dialog_payloads()


def downgrade() -> None:
    _decrypt_text_columns(
        table="notes",
        columns=("title", "content", "source_chat_title", "forward_sender_name"),
    )
    _decrypt_text_columns(table="reminders", columns=("text", "error_text"))
    _decrypt_text_columns(
        table="ai_request_logs",
        columns=("user_text", "prompt", "raw_response", "error_text"),
    )
    _decrypt_dialog_payloads()
    with op.batch_alter_table("dialog_states") as batch_op:
        batch_op.alter_column(
            "payload",
            existing_type=sa.Text(),
            type_=sa.JSON(),
            existing_nullable=False,
        )


def _encrypt_text_columns(*, table: str, columns: tuple[str, ...]) -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text(f"SELECT id, {', '.join(columns)} FROM {table}"))
    for row in rows.mappings():
        values: dict[str, Any] = {}
        for column in columns:
            value = row[column]
            if value is None or is_encrypted(value):
                continue
            values[column] = encrypt_text(str(value))
        if values:
            _update_row(table=table, row_id=row["id"], values=values)


def _decrypt_text_columns(*, table: str, columns: tuple[str, ...]) -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text(f"SELECT id, {', '.join(columns)} FROM {table}"))
    for row in rows.mappings():
        values: dict[str, Any] = {}
        for column in columns:
            value = row[column]
            if value is None or not is_encrypted(value):
                continue
            values[column] = decrypt_text(value)
        if values:
            _update_row(table=table, row_id=row["id"], values=values)


def _encrypt_dialog_payloads() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, payload FROM dialog_states"))
    for row in rows.mappings():
        value = row["payload"]
        if isinstance(value, str) and is_encrypted(value):
            continue
        payload = _coerce_payload(value)
        _update_row(
            table="dialog_states",
            row_id=row["id"],
            values={"payload": encrypt_json(payload)},
        )


def _decrypt_dialog_payloads() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text("SELECT id, payload FROM dialog_states"))
    for row in rows.mappings():
        value = row["payload"]
        payload = decrypt_json(value)
        _update_row(
            table="dialog_states",
            row_id=row["id"],
            values={"payload": json.dumps(payload, ensure_ascii=False)},
        )


def _coerce_payload(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            data = json.loads(value)
        except json.JSONDecodeError:
            return {"value": value}
        if isinstance(data, dict):
            return data
    return {"value": value}


def _update_row(*, table: str, row_id: int, values: dict[str, Any]) -> None:
    assignments = ", ".join(f"{column} = :{column}" for column in values)
    params = {"id": row_id, **values}
    op.get_bind().execute(
        sa.text(f"UPDATE {table} SET {assignments} WHERE id = :id"),
        params,
    )
