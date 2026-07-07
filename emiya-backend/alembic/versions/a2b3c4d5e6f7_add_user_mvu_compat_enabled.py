"""add user.mvu_compat_enabled toggle

Revision ID: a2b3c4d5e6f7
Revises: d1e2f3a4b5c6
Create Date: 2026-07-07

MVU 兼容总开关（CARD-0002）：账户级布尔，仅作用于聊天时。关闭后把 MVU 卡当普通卡。
server_default=true（默认开，保现有 MVU 卡开箱兼容）。不影响导入/检测/导出。
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "mvu_compat_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "mvu_compat_enabled")
