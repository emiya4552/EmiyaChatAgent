"""add conversation.analyze_emotion toggle

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-06-28

emotion 没有 template block，独立 conv 级开关；关闭后跳过 LLM 情绪分析。
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "analyze_emotion",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("conversations", "analyze_emotion")
