"""extension Vinted : republication différenciée

Revision ID: a6e4c1f8b937
Revises: f3d9b2c6e815
Create Date: 2026-10-25 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a6e4c1f8b937"
down_revision: str | Sequence[str] | None = "f3d9b2c6e815"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("article", sa.Column("derniere_publication_le", sa.DateTime(timezone=True), nullable=True))
    op.add_column("article", sa.Column("republications", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("article", "republications")
    op.drop_column("article", "derniere_publication_le")
