"""remove system_prompt_override from personas

Revision ID: 9a1b2c3d4e5f
Revises: f6a7b8c9d0e1
Create Date: 2026-06-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '9a1b2c3d4e5f'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('personas', 'system_prompt_override')


def downgrade() -> None:
    op.add_column('personas', sa.Column('system_prompt_override', sa.Text(), nullable=True))
