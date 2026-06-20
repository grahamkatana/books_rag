"""add edition_pinned to books

Revision ID: f948dc71518f
Revises: 4627f58c2d3e
Create Date: 2026-06-20 10:17:03.712762

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f948dc71518f'
down_revision: Union[str, Sequence[str], None] = '4627f58c2d3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table('books', schema=None) as batch_op:
        batch_op.add_column(sa.Column('edition_pinned', sa.Boolean(), nullable=False, server_default=sa.false()))

    # The server_default was only needed to backfill existing rows during
    # the ALTER TABLE itself -- drop it afterward since the ORM's Python-level
    # default=False (in app/models/book.py) handles every future insert.
    with op.batch_alter_table('books', schema=None) as batch_op:
        batch_op.alter_column('edition_pinned', server_default=None)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('books', schema=None) as batch_op:
        batch_op.drop_column('edition_pinned')
