"""add user.default_analyze_emotion preference

Revision ID: d1e2f3a4b5c6
Revises: e1a8d0c2b3a4
Create Date: 2026-07-06

感知系统默认偏好（ADR-0020）：账户级布尔，仅决定新建对话时
Conversation.analyze_emotion 的初始值。server_default=false → 感知 opt-in，
所有用户（新老一视同仁）默认关。不追溯已存在的对话。
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "e1a8d0c2b3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "default_analyze_emotion",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "default_analyze_emotion")
