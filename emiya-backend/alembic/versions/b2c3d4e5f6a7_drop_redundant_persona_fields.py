"""drop redundant persona fields

Revision ID: b2c3d4e5f6a7
Revises: 3267ef6a070f
Create Date: 2026-06-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = '3267ef6a070f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('personas', 'mood_spectrum')
    op.drop_column('personas', 'mbti')
    op.drop_column('personas', 'backstory')
    op.drop_column('personas', 'backstory_short')
    op.drop_column('personas', 'speech_style')


def downgrade() -> None:
    op.add_column('personas', sa.Column('speech_style', postgresql.JSONB(), nullable=True))
    op.add_column('personas', sa.Column('backstory_short', sa.String(80), nullable=True))
    op.add_column('personas', sa.Column('backstory', sa.Text(), nullable=True))
    op.add_column('personas', sa.Column('mbti', sa.String(4), nullable=True))
    op.add_column('personas', sa.Column('mood_spectrum', postgresql.JSONB(), nullable=True))
