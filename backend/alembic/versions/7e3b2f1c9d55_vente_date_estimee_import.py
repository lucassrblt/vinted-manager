"""vente : date estimée de l'import remplacée par la vraie date du mail

Revision ID: 7e3b2f1c9d55
Revises: 5c1d7e9a2b40
Create Date: 2026-10-21 19:10:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7e3b2f1c9d55"
down_revision: str | Sequence[str] | None = "5c1d7e9a2b40"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("vente", sa.Column("date_estimee_import", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("vente", "date_estimee_import")
