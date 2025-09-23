"""Add search preference table

Revision ID: 20240715_120000
Revises: 20240612_120000
Create Date: 2024-07-15 12:00:00
"""

from alembic import op
import sqlalchemy as sa


revision = "20240715_120000"
down_revision = "20240612_120000"
branch_labels = None
depends_on = None


_search_preference_table = sa.table(
    "search_preference",
    sa.column("id", sa.Integer),
    sa.column("quality_priority", sa.Integer),
    sa.column("voice_priority", sa.Integer),
    sa.column("size_priority", sa.Integer),
)


def upgrade():
    op.create_table(
        "search_preference",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("quality_priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("voice_priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("size_priority", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )

    op.bulk_insert(
        _search_preference_table,
        [
            {
                "id": 1,
                "quality_priority": 0,
                "voice_priority": 0,
                "size_priority": 0,
            }
        ],
    )



def downgrade():
    op.drop_table("search_preference")
