"""add conversations.mvu_capabilities + messages.data (ADR-0008d)

Revision ID: e1a8d0c2b3a4
Revises: e0f1a2b3c4d5
Create Date: 2026-07-05

ADR-0008d 卡 UI 挂载 + 重能力限权：
  - conversations.mvu_capabilities：per-conversation 危险能力 opt-in（默认 {} = 全拒）。
  - messages.data：TavernHelper `data`（每条消息变量袋），卡 UI（飞讯手机终端）经能力端点读写。
两列都可空/有默认，附加式，off 时零行为变化。

注：本迁移原 revision id `a7b8c9d0e1f2` 与另一条迁移重号、且原 down_revision
`f1a2b3c4d5e6` 未随分支提交（孤儿）。已在 ADR-0020 落地时重认领：唯一 id +
接到真实 head e0f1a2b3c4d5。两列此前已存在于运行库中（stamp 校正历史，详见 ADR-0020）。
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e1a8d0c2b3a4"
down_revision: Union[str, None] = "e0f1a2b3c4d5"
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
