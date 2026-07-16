"""add user account_config

Revision ID: a4b5c6d7e8f9
Revises: f2a3b4c5d6e7
Create Date: 2026-07-15

账户级配置桶（配置系统 ADR-4）：单个 JSONB 承载记忆系统偏好（总开关/提取频率/检索旋钮）
+ token 预算账户默认。键/默认/钳制/白名单由 config_registry 统一管；空 {} = 全部继承全局。
存量行 server_default '{}' 回填，行为不变。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a4b5c6d7e8f9"
down_revision: Union[str, None] = "f2a3b4c5d6e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "account_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "account_config")
