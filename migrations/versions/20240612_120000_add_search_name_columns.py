"""Add search_name columns to movie and library_movie

Revision ID: 20240612_120000
Revises: 20240228_000001
Create Date: 2024-06-12 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20240612_120000"
down_revision = "20240228_000001"
branch_labels = None
depends_on = None


def _has_column(table_name: str, column_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [col["name"] for col in inspector.get_columns(table_name)]
    return column_name in columns


def upgrade():
    if not _has_column("movie", "search_name"):
        op.add_column(
            "movie",
            sa.Column("search_name", sa.String(length=200), nullable=True),
        )

    if not _has_column("library_movie", "search_name"):
        op.add_column(
            "library_movie",
            sa.Column("search_name", sa.String(length=200), nullable=True),
        )

    op.execute("UPDATE movie SET search_name = name WHERE search_name IS NULL")
    op.execute(
        "UPDATE library_movie SET search_name = name WHERE search_name IS NULL"
    )


def downgrade():
    if _has_column("library_movie", "search_name"):
        op.drop_column("library_movie", "search_name")

    if _has_column("movie", "search_name"):
        op.drop_column("movie", "search_name")
