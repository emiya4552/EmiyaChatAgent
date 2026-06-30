"""create presets table and add chat_config to conversations

Revision ID: f0e1d2c3b4a5
Revises: e7f8a9b0c1d2
Create Date: 2026-06-26
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "f0e1d2c3b4a5"
down_revision: Union[str, None] = "c0d1e2f3a4b5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "presets",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sampling_params", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("context_settings", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("prompts", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("extensions", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.add_column("conversations", sa.Column("chat_config", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")))
    op.add_column("conversations", sa.Column("preset_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_conversations_preset_id", "conversations", "presets", ["preset_id"], ["id"], ondelete="SET NULL")
    op.drop_column("conversations", "preset_name")


def downgrade() -> None:
    op.add_column("conversations", sa.Column("preset_name", sa.String(100), nullable=True))
    op.drop_constraint("fk_conversations_preset_id", "conversations", type_="foreignkey")
    op.drop_column("conversations", "preset_id")
    op.drop_column("conversations", "chat_config")
    op.drop_table("presets")
