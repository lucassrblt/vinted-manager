"""article : pièce perso

Revision ID: b2e8f4a61c07
Revises: 9a4c6d2e8f13
Create Date: 2026-10-21 22:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2e8f4a61c07"
down_revision: str | Sequence[str] | None = "9a4c6d2e8f13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("article", sa.Column("perso", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("article", "perso")
