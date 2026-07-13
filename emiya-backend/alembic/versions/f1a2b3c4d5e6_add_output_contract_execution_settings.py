"""add output contract execution settings

Revision ID: f1a2b3c4d5e6
Revises: c0af210d230b
Create Date: 2026-07-10

账户级可见输出契约聊天期执行默认（ADR-1f）：默认执行模式 auto、是否允许整篇
rewrite（默认关）、strict 降级模式（默认 repair）。对话级覆盖存 chat_config，不建列。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, None] = "c0af210d230b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "output_contract_default_mode",
            sa.String(length=16),
            nullable=False,
            server_default="auto",
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "output_contract_allow_full_rewrite",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "output_contract_strict_fallback",
            sa.String(length=16),
            nullable=False,
            server_default="repair",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "output_contract_strict_fallback")
    op.drop_column("users", "output_contract_allow_full_rewrite")
    op.drop_column("users", "output_contract_default_mode")
