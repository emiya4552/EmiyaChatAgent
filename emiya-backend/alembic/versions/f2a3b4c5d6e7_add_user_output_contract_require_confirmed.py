"""add user output_contract_require_confirmed

Revision ID: f2a3b4c5d6e7
Revises: f1a2b3c4d5e6
Create Date: 2026-07-14

账户级「严格声明模式」默认（ADR-2c / 配置系统 ADR）：补齐此前缺失的账户层——
此前该开关只有全局 settings.OUTPUT_CONTRACT_REQUIRE_CONFIRMED 与对话 chat_config
覆盖，独缺账户默认，导致 policy.resolve_require_confirmed 的账户分支恒拿不到值。

**可空**列（NULL=继承全局）：唯有此项同时有全局 env 层，用非空默认会永久遮蔽全局；
存量行 NULL → 保持现有「按全局默认」行为不变，用户在设置页显式表态后才覆盖。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 可空、无 server_default：存量与新行均为 NULL = 继承全局默认。
    op.add_column(
        "users",
        sa.Column(
            "output_contract_require_confirmed",
            sa.Boolean(),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "output_contract_require_confirmed")
