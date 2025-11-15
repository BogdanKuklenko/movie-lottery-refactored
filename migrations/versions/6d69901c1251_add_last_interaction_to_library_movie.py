"""add last interaction timestamp to library movie

Revision ID: 6d69901c1251
Revises: f3443ff64408
Create Date: 2025-02-15 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6d69901c1251'
down_revision = 'f3443ff64408'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'library_movie',
        sa.Column('last_interaction_at', sa.DateTime(), server_default=sa.func.now(), nullable=False)
    )
    op.execute('UPDATE library_movie SET last_interaction_at = added_at')
    op.alter_column(
        'library_movie',
        'last_interaction_at',
        existing_type=sa.DateTime(),
        server_default=None
    )


def downgrade():
    op.drop_column('library_movie', 'last_interaction_at')
