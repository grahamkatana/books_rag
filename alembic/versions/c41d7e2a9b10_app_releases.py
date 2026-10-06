"""app releases

Revision ID: c41d7e2a9b10
Revises: 8401efabb5d1
Create Date: 2026-10-06 17:00:00

Two new tables for published Android app versions. Nothing existing is touched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c41d7e2a9b10'
down_revision: Union[str, Sequence[str], None] = '8401efabb5d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'app_releases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('version_name', sa.String(length=40), nullable=False),
        sa.Column('version_code', sa.Integer(), nullable=False),
        sa.Column('size_bytes', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('uploaded_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id'], name=op.f('fk_app_releases_uploaded_by_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_app_releases')),
        sa.UniqueConstraint('version_code', name=op.f('uq_app_releases_version_code')),
    )
    op.create_table(
        'app_release_files',
        sa.Column('release_id', sa.Integer(), nullable=False),
        sa.Column('data', sa.LargeBinary(), nullable=False),
        sa.ForeignKeyConstraint(['release_id'], ['app_releases.id'], name=op.f('fk_app_release_files_release_id_app_releases'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('release_id', name=op.f('pk_app_release_files')),
    )


def downgrade() -> None:
    op.drop_table('app_release_files')
    op.drop_table('app_releases')
