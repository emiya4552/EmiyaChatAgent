"""drop dead profile tables (replaced by unified Persona)

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('conversation_profiles')
    op.drop_table('user_profiles')


def downgrade() -> None:
    op.create_table('user_profiles',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('user_id', postgresql.UUID(), nullable=False),
        sa.Column('nickname', sa.String(50), nullable=True),
        sa.Column('gender', sa.String(10), nullable=True),
        sa.Column('age_range', sa.String(20), nullable=True),
        sa.Column('personality_type', sa.String(4), nullable=True),
        sa.Column('personality_traits', postgresql.JSONB(), nullable=True),
        sa.Column('interests', postgresql.JSONB(), nullable=True),
        sa.Column('communication_style', sa.String(20), nullable=True),
        sa.Column('avoid_topics', postgresql.JSONB(), nullable=True),
        sa.Column('goal', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id'),
    )
    op.create_table('conversation_profiles',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('conversation_id', postgresql.UUID(), nullable=False),
        sa.Column('role_override', sa.String(50), nullable=True),
        sa.Column('tone_preference', sa.String(20), nullable=True),
        sa.Column('special_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('conversation_id'),
    )
