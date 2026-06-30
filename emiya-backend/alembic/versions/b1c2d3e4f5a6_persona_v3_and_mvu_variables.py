"""persona v3 fields (alternate_greetings/scenario) + MVU variable buckets

Revision ID: b1c2d3e4f5a6
Revises: a8b9c0d1e2f3
Create Date: 2026-06-28

详见：
  docs/adr/0006-persona-v3-field-expansion.md
  docs/adr/0007-mvu-scope-and-rendering-pipeline.md
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── personas: v3 字段 ──
    op.add_column(
        "personas",
        sa.Column(
            "alternate_greetings",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column("personas", sa.Column("scenario", sa.Text(), nullable=True))

    # ── conversations: MVU 本地变量桶 ──
    op.add_column(
        "conversations",
        sa.Column(
            "variables",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )

    # ── users: MVU 全局变量桶 ──
    op.add_column(
        "users",
        sa.Column(
            "global_variables",
            JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "global_variables")
    op.drop_column("conversations", "variables")
    op.drop_column("personas", "scenario")
    op.drop_column("personas", "alternate_greetings")
