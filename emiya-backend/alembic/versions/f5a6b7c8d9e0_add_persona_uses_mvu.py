"""add personas.uses_mvu (MVU compat v0)

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-06-28

详见 docs/adr/0010-mvu-compat-v0.md
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "personas",
        sa.Column(
            "uses_mvu",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("personas", "uses_mvu")
