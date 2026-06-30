"""unify personas: add type/interests/goal, drop greeting, replace user_personas

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-06-17
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add new columns to personas
    op.add_column('personas',
        sa.Column('type', sa.String(10), nullable=False, server_default='ai'))
    op.add_column('personas',
        sa.Column('interests', postgresql.JSONB(), nullable=True))
    op.add_column('personas',
        sa.Column('goal', sa.String(50), nullable=True))

    # 2. Drop greeting from personas
    op.drop_column('personas', 'greeting')

    # 3. NULL out all user_persona_id (old FK values will be invalid)
    op.execute("UPDATE conversations SET user_persona_id = NULL")

    # 4. Drop old FK constraint
    op.drop_constraint('conversations_user_persona_id_fkey', 'conversations', type_='foreignkey')

    # 5. Drop user_personas table
    op.drop_table('user_personas')

    # 6. Re-add FK pointing to personas
    op.create_foreign_key(
        'conversations_user_persona_id_fkey',
        'conversations', 'personas',
        ['user_persona_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    # 1. Drop FK to personas
    op.drop_constraint('conversations_user_persona_id_fkey', 'conversations', type_='foreignkey')

    # 2. Recreate user_personas table
    op.create_table('user_personas',
        sa.Column('id', postgresql.UUID(), nullable=False),
        sa.Column('user_id', postgresql.UUID(), nullable=True),
        sa.Column('name', sa.String(50), nullable=False),
        sa.Column('description', sa.String(100), nullable=True),
        sa.Column('gender', sa.String(10), nullable=True),
        sa.Column('age_range', sa.String(10), nullable=True),
        sa.Column('personality_type', sa.String(4), nullable=True),
        sa.Column('personality_traits', postgresql.JSONB(), nullable=True),
        sa.Column('interests', postgresql.JSONB(), nullable=True),
        sa.Column('communication_style', sa.String(20), nullable=False, server_default='casual'),
        sa.Column('avoid_topics', postgresql.JSONB(), nullable=True),
        sa.Column('goal', sa.String(50), nullable=False, server_default='陪伴'),
        sa.Column('is_template', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # 3. Re-add FK to user_personas
    op.create_foreign_key(
        'conversations_user_persona_id_fkey',
        'conversations', 'user_personas',
        ['user_persona_id'], ['id'],
        ondelete='SET NULL',
    )

    # 4. Re-add greeting
    op.add_column('personas', sa.Column('greeting', sa.Text(), nullable=True))

    # 5. Remove new columns
    op.drop_column('personas', 'goal')
    op.drop_column('personas', 'interests')
    op.drop_column('personas', 'type')
