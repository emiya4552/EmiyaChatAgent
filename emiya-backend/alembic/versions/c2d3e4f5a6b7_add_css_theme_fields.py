"""add css_theme to users and personas (frontend rendering / CSS themes)

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-06-28

详见 docs/adr/0008-frontend-rendering-and-css-theme.md
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "c2d3e4f5a6b7"
down_revision: Union[str, None] = "b1c2d3e4f5a6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("css_theme", sa.Text(), nullable=True))
    op.add_column("personas", sa.Column("css_theme", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("personas", "css_theme")
    op.drop_column("users", "css_theme")
