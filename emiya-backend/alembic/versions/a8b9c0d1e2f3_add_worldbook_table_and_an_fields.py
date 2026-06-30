"""add worldbook table + persona.default_worldbook_ids/author_note + conversation.worldbook_ids/AN fields

Revision ID: a8b9c0d1e2f3
Revises: f0e1d2c3b4a5
Create Date: 2026-06-27
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision: str = "a8b9c0d1e2f3"
down_revision: Union[str, None] = "f0e1d2c3b4a5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 新表 worldbooks ──
    op.create_table(
        "worldbooks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scan_depth", sa.Integer(), nullable=False, server_default="2"),
        sa.Column("case_sensitive", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("match_whole_words", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("entries", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("extensions", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_worldbooks_user_id", "worldbooks", ["user_id"])

    # ── personas 加默认推荐字段 ──
    op.add_column(
        "personas",
        sa.Column("default_worldbook_ids", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column("personas", sa.Column("author_note", sa.Text(), nullable=True))

    # ── conversations 加绑定 + AN 字段 ──
    op.add_column(
        "conversations",
        sa.Column("worldbook_ids", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column("conversations", sa.Column("author_note", sa.Text(), nullable=True))
    op.add_column(
        "conversations",
        sa.Column("an_depth", sa.Integer(), nullable=False, server_default="4"),
    )
    op.add_column(
        "conversations",
        sa.Column("an_role", sa.String(20), nullable=False, server_default="system"),
    )
    op.add_column(
        "conversations",
        sa.Column("an_interval", sa.Integer(), nullable=False, server_default="1"),
    )


def downgrade() -> None:
    op.drop_column("conversations", "an_interval")
    op.drop_column("conversations", "an_role")
    op.drop_column("conversations", "an_depth")
    op.drop_column("conversations", "author_note")
    op.drop_column("conversations", "worldbook_ids")

    op.drop_column("personas", "author_note")
    op.drop_column("personas", "default_worldbook_ids")

    op.drop_index("ix_worldbooks_user_id", table_name="worldbooks")
    op.drop_table("worldbooks")
