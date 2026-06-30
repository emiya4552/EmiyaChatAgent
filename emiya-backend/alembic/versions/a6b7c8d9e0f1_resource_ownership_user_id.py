"""add user_id to presets / regex_presets / prompt_templates (resource ownership)

Revision ID: a6b7c8d9e0f1
Revises: f5a6b7c8d9e0
Create Date: 2026-06-29

详见 docs/adr/0013-resource-ownership.md
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a6b7c8d9e0f1"
down_revision: Union[str, None] = "f5a6b7c8d9e0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. 三表加 user_id（先 nullable，以便给历史数据 UPDATE）
    for table in ("presets", "regex_presets", "prompt_templates"):
        op.add_column(
            table,
            sa.Column("user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        )
        op.create_foreign_key(
            f"fk_{table}_user_id",
            table,
            "users",
            ["user_id"],
            ["id"],
            ondelete="CASCADE",
        )

    # 2. 历史数据归属：选择 created_at 最早的用户作为归属对象
    op.execute(
        "UPDATE presets SET user_id = (SELECT id FROM users ORDER BY created_at LIMIT 1)"
    )
    op.execute(
        "UPDATE regex_presets SET user_id = (SELECT id FROM users ORDER BY created_at LIMIT 1)"
    )
    op.execute(
        "UPDATE prompt_templates SET user_id = (SELECT id FROM users ORDER BY created_at LIMIT 1)"
    )

    # 3. Preset / RegexPreset 改为 NOT NULL（PromptTemplate 仍 nullable，预留系统模板）
    op.alter_column("presets", "user_id", nullable=False)
    op.alter_column("regex_presets", "user_id", nullable=False)


def downgrade() -> None:
    for table in ("presets", "regex_presets", "prompt_templates"):
        op.drop_constraint(f"fk_{table}_user_id", table, type_="foreignkey")
        op.drop_column(table, "user_id")
