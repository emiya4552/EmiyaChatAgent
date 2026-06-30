"""add scope and memory_type to memories

Revision ID: a1b2c3d4e5f6
Revises: 6028c1b37f18
Create Date: 2026-06-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '6028c1b37f18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('memories',
        sa.Column('scope', sa.String(50), nullable=False, server_default='global'))
    op.add_column('memories',
        sa.Column('memory_type', sa.String(20), nullable=False, server_default='fact'))
    # 存量数据已由 server_default 填充，无需额外 UPDATE


def downgrade() -> None:
    op.drop_column('memories', 'memory_type')
    op.drop_column('memories', 'scope')
