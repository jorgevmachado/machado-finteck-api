"""scheduled transaction occurrence unique

Revision ID: b7c2e41f8d90
Revises: 9fc4f731e471
Create Date: 2026-11-24 16:55:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7c2e41f8d90"
down_revision: Union[str, Sequence[str], None] = "9fc4f731e471"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DUPLICATES_QUERY = sa.text(
    """
    SELECT transaction_series_id, occurrence_index, COUNT(*) AS total
    FROM scheduled_transactions
    WHERE deleted_at IS NULL
    GROUP BY transaction_series_id, occurrence_index
    HAVING COUNT(*) > 1
    """
)


def upgrade() -> None:
    """Upgrade schema."""
    duplicates = op.get_bind().execute(_DUPLICATES_QUERY).fetchall()
    if duplicates:
        rendered = ", ".join(
            f"(series={row.transaction_series_id}, index={row.occurrence_index}, "
            f"total={row.total})"
            for row in duplicates
        )
        raise RuntimeError(
            "Cannot create unique constraint on scheduled_transactions: "
            f"duplicate occurrences found: {rendered}. "
            "Resolve the duplicates before applying this migration."
        )

    op.create_index(
        "uq_scheduled_transactions_series_occurrence",
        "scheduled_transactions",
        ["transaction_series_id", "occurrence_index"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_scheduled_transactions_series_occurrence",
        table_name="scheduled_transactions",
    )