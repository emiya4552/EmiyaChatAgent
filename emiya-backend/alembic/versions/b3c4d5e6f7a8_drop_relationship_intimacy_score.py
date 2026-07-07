"""drop relationships.intimacy_score (dead legacy column)

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-07-07

intimacy_score 早已被 affinity_score 取代、代码零读写（模型注释自承"保留 DB 列以避免
迁移"）。死代码清理时一并 drop。downgrade 重建列（Float, default 0）。
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("relationships", "intimacy_score")


def downgrade() -> None:
    op.add_column(
        "relationships",
        sa.Column(
            "intimacy_score",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )
