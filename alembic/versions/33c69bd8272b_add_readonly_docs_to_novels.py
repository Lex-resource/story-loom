"""add readonly_docs to novels

Revision ID: 33c69bd8272b
Revises: a67ec1f3e3f7
Create Date: 2026-06-25 17:40:17.460312

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '33c69bd8272b'
down_revision: Union[str, Sequence[str], None] = 'a67ec1f3e3f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('novels', sa.Column('readonly_docs', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('novels', 'readonly_docs')
