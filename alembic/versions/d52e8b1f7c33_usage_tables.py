"""usage tables

Revision ID: d52e8b1f7c33
Revises: c41d7e2a9b10
Create Date: 2026-10-07 18:30:00

Three new tables: AI usage events, per-model prices, and manually entered provider credit. Nothing existing is touched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd52e8b1f7c33'
down_revision: Union[str, Sequence[str], None] = 'c41d7e2a9b10'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'usage_events',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('kind', sa.String(20), nullable=False),
        sa.Column('provider', sa.String(40), nullable=False),
        sa.Column('model', sa.String(100), nullable=False),
        sa.Column('input_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('output_tokens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('estimated', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index('ix_usage_events_created_at', 'usage_events', ['created_at'])
    op.create_table(
        'model_prices',
        sa.Column('provider', sa.String(40), primary_key=True),
        sa.Column('model', sa.String(100), primary_key=True),
        sa.Column('input_per_million', sa.Numeric(12, 4), nullable=False),
        sa.Column('output_per_million', sa.Numeric(12, 4), nullable=False),
        sa.Column('note', sa.String(200), nullable=False, server_default=''),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )
    op.create_table(
        'provider_credits',
        sa.Column('provider', sa.String(40), primary_key=True),
        sa.Column('amount_usd', sa.Numeric(12, 4), nullable=False),
        sa.Column('as_of', sa.DateTime(), nullable=False),
    )
    op.execute("INSERT INTO model_prices (provider, model, input_per_million, output_per_million, note, updated_at) "
               "VALUES ('openai', 'text-embedding-3-large', 0.13, 0, 'seeded; confirm on the OpenAI pricing page', CURRENT_TIMESTAMP)")


def downgrade() -> None:
    op.drop_table('provider_credits')
    op.drop_table('model_prices')
    op.drop_index('ix_usage_events_created_at', table_name='usage_events')
    op.drop_table('usage_events')
