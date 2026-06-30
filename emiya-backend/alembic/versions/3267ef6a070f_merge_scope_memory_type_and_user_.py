"""merge scope/memory_type and user_personas branches

Revision ID: 3267ef6a070f
Revises: 24361230c945, a1b2c3d4e5f6
Create Date: 2026-06-17 12:01:32.937727

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3267ef6a070f'
down_revision: Union[str, None] = ('24361230c945', 'a1b2c3d4e5f6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
