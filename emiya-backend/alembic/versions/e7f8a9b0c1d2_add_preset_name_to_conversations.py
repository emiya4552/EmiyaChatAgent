"""add preset_name to conversations

Revision ID: e7f8a9b0c1d2
Revises: d5e6f7a8b9c0
Create Date: 2026-06-25
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'e7f8a9b0c1d2'
down_revision: Union[str, None] = 'd5e6f7a8b9c0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('conversations', sa.Column('preset_name', sa.String(100), nullable=True))


def downgrade() -> None:
    op.drop_column('conversations', 'preset_name')
