"""Add note categories.

Revision ID: 202607280002
Revises: 202607270001
Create Date: 2026-07-28
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "202607280002"
down_revision: str | None = "202607270001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "note_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("normalized_name", sa.String(length=100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_note_categories_user_id_users"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_note_categories")),
        sa.UniqueConstraint(
            "user_id",
            "normalized_name",
            name="uq_note_categories_user_id_normalized_name",
        ),
    )
    op.create_index(
        op.f("ix_note_categories_normalized_name"),
        "note_categories",
        ["normalized_name"],
    )
    op.create_index(
        op.f("ix_note_categories_user_id"),
        "note_categories",
        ["user_id"],
    )

    with op.batch_alter_table("notes") as batch_op:
        batch_op.add_column(sa.Column("category_id", sa.Integer(), nullable=True))
        batch_op.create_index(op.f("ix_notes_category_id"), ["category_id"])
        batch_op.create_foreign_key(
            op.f("fk_notes_category_id_note_categories"),
            "note_categories",
            ["category_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("notes") as batch_op:
        batch_op.drop_constraint(
            op.f("fk_notes_category_id_note_categories"),
            type_="foreignkey",
        )
        batch_op.drop_index(op.f("ix_notes_category_id"))
        batch_op.drop_column("category_id")

    op.drop_index(op.f("ix_note_categories_user_id"), table_name="note_categories")
    op.drop_index(
        op.f("ix_note_categories_normalized_name"),
        table_name="note_categories",
    )
    op.drop_table("note_categories")
