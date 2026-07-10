"""add output contract detection settings

Revision ID: c0af210d230b
Revises: b3c4d5e6f7a8
Create Date: 2026-07-09

账户级世界书输出契约自动识别设置。默认关闭 LLM 自动识别，默认每次批量最多
检测 30 条候选 entry。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c0af210d230b"
down_revision: Union[str, None] = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "output_contract_llm_detection_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "users",
        sa.Column(
            "output_contract_llm_detection_limit",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "output_contract_llm_detection_limit")
    op.drop_column("users", "output_contract_llm_detection_enabled")
