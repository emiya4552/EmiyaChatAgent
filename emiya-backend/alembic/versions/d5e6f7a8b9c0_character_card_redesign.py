"""character card redesign: add card fields, migrate legacy data to card_data JSONB, drop redundant columns

Revision ID: d5e6f7a8b9c0
Revises: b9c0d1e2f3a4
Create Date: 2026-06-25
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'd5e6f7a8b9c0'
down_revision: Union[str, None] = 'b9c0d1e2f3a4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: add new columns (all nullable)
    op.add_column('personas', sa.Column('first_message', sa.Text(), nullable=True))
    op.add_column('personas', sa.Column('mes_example', sa.Text(), nullable=True))
    op.add_column('personas', sa.Column('system_prompt_override', sa.Text(), nullable=True))
    op.add_column('personas', sa.Column('tags', postgresql.JSONB, nullable=True))
    op.add_column('personas', sa.Column('avatar_url', sa.String(500), nullable=True))
    op.add_column('personas', sa.Column('card_data', postgresql.JSONB, nullable=True))
    op.add_column('personas', sa.Column('source', sa.String(20), nullable=False, server_default='manual'))
    op.add_column('personas', sa.Column('source_url', sa.String(500), nullable=True))
    op.add_column('personas', sa.Column('imported_at', sa.DateTime(), nullable=True))

    # Mark existing templates
    op.execute("UPDATE personas SET source = 'template' WHERE is_template = TRUE")

    # Step 2: migrate legacy column data into card_data JSONB before dropping
    op.execute("""
        UPDATE personas
        SET card_data = jsonb_build_object(
            'type', type,
            'speaking_style', speaking_style,
            'gender', gender,
            'age', age,
            'interests', CASE WHEN interests IS NOT NULL THEN to_jsonb(interests) ELSE NULL END,
            'quirks', CASE WHEN quirks IS NOT NULL THEN to_jsonb(quirks) ELSE NULL END,
            'constraints', constraints,
            'goal', goal
        )
        WHERE type IS NOT NULL
           OR speaking_style IS NOT NULL
           OR gender IS NOT NULL
           OR age IS NOT NULL
           OR interests IS NOT NULL
           OR quirks IS NOT NULL
           OR constraints IS NOT NULL
           OR goal IS NOT NULL
    """)

    # Step 3: drop legacy columns
    for col in ['type', 'speaking_style', 'gender', 'age', 'interests',
                'quirks', 'constraints', 'goal']:
        op.drop_column('personas', col)


def downgrade() -> None:
    # Restore legacy columns
    op.add_column('personas', sa.Column('type', sa.String(10), nullable=False, server_default='ai'))
    op.add_column('personas', sa.Column('speaking_style', sa.Text(), nullable=True))
    op.add_column('personas', sa.Column('gender', sa.String(10), nullable=True))
    op.add_column('personas', sa.Column('age', sa.String(50), nullable=True))
    op.add_column('personas', sa.Column('interests', postgresql.JSONB, nullable=True))
    op.add_column('personas', sa.Column('quirks', postgresql.JSONB, nullable=True))
    op.add_column('personas', sa.Column('constraints', sa.Text(), nullable=True))
    op.add_column('personas', sa.Column('goal', sa.String(50), nullable=True))

    # Restore data from card_data
    op.execute("""
        UPDATE personas SET
            type = COALESCE(card_data->>'type', 'ai'),
            speaking_style = card_data->>'speaking_style',
            gender = card_data->>'gender',
            age = card_data->>'age',
            interests = CASE
                WHEN card_data->'interests' IS NOT NULL AND jsonb_typeof(card_data->'interests') = 'array'
                THEN card_data->'interests'
                ELSE NULL
            END,
            quirks = CASE
                WHEN card_data->'quirks' IS NOT NULL AND jsonb_typeof(card_data->'quirks') = 'array'
                THEN card_data->'quirks'
                ELSE NULL
            END,
            constraints = card_data->>'constraints',
            goal = card_data->>'goal'
        WHERE card_data IS NOT NULL
    """)

    # Drop new columns
    for col in ['first_message', 'mes_example', 'system_prompt_override',
                'tags', 'avatar_url', 'card_data',
                'source', 'source_url', 'imported_at']:
        op.drop_column('personas', col)
