"""merge prompt_templates and preset_name heads

Revision ID: c0d1e2f3a4b5
Revises: b0c1d2e3f4a5, e7f8a9b0c1d2
Create Date: 2026-06-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c0d1e2f3a4b5'
down_revision: Union[str, Sequence[str], None] = ('b0c1d2e3f4a5', 'e7f8a9b0c1d2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
