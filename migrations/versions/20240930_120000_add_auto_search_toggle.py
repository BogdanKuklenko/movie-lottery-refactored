"""Add auto search toggle to search preferences"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20240930_120000_add_auto_search_toggle"
down_revision = "20240715_120000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "search_preference",
        sa.Column(
            "auto_search_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("search_preference", "auto_search_enabled")
