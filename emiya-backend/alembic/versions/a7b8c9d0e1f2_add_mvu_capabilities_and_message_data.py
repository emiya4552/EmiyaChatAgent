"""add conversations.mvu_capabilities + messages.data (ADR-0008d)

Revision ID: a7b8c9d0e1f2
Revises: f1a2b3c4d5e6
Create Date: 2026-07-05

ADR-0008d 卡 UI 挂载 + 重能力限权：
  - conversations.mvu_capabilities：per-conversation 危险能力 opt-in（默认 {} = 全拒）。
  - messages.data：TavernHelper `data`（每条消息变量袋），卡 UI（飞讯手机终端）经能力端点读写。
两列都可空/有默认，附加式，off 时零行为变化。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a7b8c9d0e1f2"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "mvu_capabilities",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "messages",
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("messages", "data")
    op.drop_column("conversations", "mvu_capabilities")
