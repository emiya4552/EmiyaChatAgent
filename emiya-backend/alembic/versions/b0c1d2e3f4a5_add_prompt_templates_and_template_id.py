"""add prompt_templates table and template_id to conversations

Revision ID: b0c1d2e3f4a5
Revises: 9a1b2c3d4e5f
Create Date: 2026-06-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = 'b0c1d2e3f4a5'
down_revision: Union[str, None] = '9a1b2c3d4e5f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'prompt_templates',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_default', sa.Boolean(), default=False),
        sa.Column('blocks', postgresql.JSONB, nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
    )
    op.add_column('conversations', sa.Column(
        'template_id', postgresql.UUID(as_uuid=True),
        sa.ForeignKey('prompt_templates.id', ondelete='SET NULL'),
        nullable=True,
    ))


def downgrade() -> None:
    op.drop_column('conversations', 'template_id')
    op.drop_table('prompt_templates')
