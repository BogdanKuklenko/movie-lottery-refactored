"""Add search_name columns to movie and library_movie

Revision ID: 20240228_000001
Revises: 
Create Date: 2024-02-28 00:00:01
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20240228_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "movie",
        sa.Column("search_name", sa.String(length=200), nullable=True),
    )
    op.add_column(
        "library_movie",
        sa.Column("search_name", sa.String(length=200), nullable=True),
    )

    op.execute("UPDATE movie SET search_name = name")
    op.execute("UPDATE library_movie SET search_name = name")


def downgrade():
    op.drop_column("library_movie", "search_name")
    op.drop_column("movie", "search_name")
