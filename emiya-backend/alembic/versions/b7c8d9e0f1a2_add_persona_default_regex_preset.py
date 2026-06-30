"""add personas.default_regex_preset_id

Revision ID: b7c8d9e0f1a2
Revises: a6b7c8d9e0f1
Create Date: 2026-06-29

卡内嵌 extensions.regex_scripts 导入时拆成 RegexPreset，并把 ID 挂到 persona。
建对话时若 preset 不带 regex_preset_id，就回退用这个。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "b7c8d9e0f1a2"
down_revision: Union[str, None] = "a6b7c8d9e0f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "personas",
        sa.Column(
            "default_regex_preset_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("regex_presets.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("personas", "default_regex_preset_id")
