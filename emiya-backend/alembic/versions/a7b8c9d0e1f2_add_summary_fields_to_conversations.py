"""add summary and last_summarized_count to conversations

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a7b8c9d0e1f2'
down_revision: Union[str, None] = 'f6a7b8c9d0e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('conversations',
        sa.Column('summary', sa.Text(), nullable=True))
    op.add_column('conversations',
        sa.Column('last_summarized_count', sa.Integer(), nullable=True))
    op.execute("UPDATE conversations SET last_summarized_count = 0 WHERE last_summarized_count IS NULL")
    op.alter_column('conversations', 'last_summarized_count', nullable=False, server_default='0')


def downgrade() -> None:
    op.drop_column('conversations', 'last_summarized_count')
    op.drop_column('conversations', 'summary')
