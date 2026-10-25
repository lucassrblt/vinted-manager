"""extension Vinted : baisse de prix automatique

Revision ID: b8f2d5a1c463
Revises: a6e4c1f8b937
Create Date: 2026-10-25 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8f2d5a1c463"
down_revision: str | Sequence[str] | None = "a6e4c1f8b937"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("article", sa.Column("baisse_prix_le", sa.DateTime(timezone=True), nullable=True))
    op.add_column("article", sa.Column("prix_avant_baisse", sa.Numeric(10, 2), nullable=True))


def downgrade() -> None:
    op.drop_column("article", "prix_avant_baisse")
    op.drop_column("article", "baisse_prix_le")
