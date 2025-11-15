"""add last interaction timestamp to library movie

Revision ID: 6d69901c1251
Revises: f3443ff64408
Create Date: 2025-02-15 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


def _column_exists(bind, table_name, column_name):
    inspector = sa.inspect(bind)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns


# revision identifiers, used by Alembic.
revision = '6d69901c1251'
down_revision = 'f3443ff64408'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not _column_exists(bind, 'library_movie', 'last_interaction_at'):
        op.add_column(
            'library_movie',
            sa.Column('last_interaction_at', sa.DateTime(), server_default=sa.func.now(), nullable=False)
        )
        op.execute('UPDATE library_movie SET last_interaction_at = added_at')

    if bind.dialect.name != 'sqlite':
        op.alter_column(
            'library_movie',
            'last_interaction_at',
            existing_type=sa.DateTime(),
            server_default=None
        )


def downgrade():
    op.drop_column('library_movie', 'last_interaction_at')
