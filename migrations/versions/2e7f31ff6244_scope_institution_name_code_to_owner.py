"""scope institution name code uniqueness to owner

Revision ID: 2e7f31ff6244
Revises: 584c97909e82
Create Date: 2026-11-04 13:14:44.824978

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "2e7f31ff6244"
down_revision: Union[str, Sequence[str], None] = "584c97909e82"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_constraint("institutions_name_code_key", "institutions", type_="unique")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_unique_constraint(
        "institutions_name_code_key", "institutions", ["name_code"]
    )
