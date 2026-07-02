"""add messages.display_content (prompt/display two-pipeline)

Revision ID: e0f1a2b3c4d5
Revises: d9e0f1a2b3c4
Create Date: 2026-07-02

docs/mvu/adr/0003 双管线：Message.content 存 prompt 真相版，display_content
存 markdownOnly 美化后的显示版。nullable，老消息为 NULL（前端回退 content）。
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "e0f1a2b3c4d5"
down_revision: Union[str, None] = "d9e0f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "messages",
        sa.Column("display_content", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "display_content")
