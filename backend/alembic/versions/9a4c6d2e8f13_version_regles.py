"""parametres : version des règles de classement par défaut

Revision ID: 9a4c6d2e8f13
Revises: 7e3b2f1c9d55
Create Date: 2026-10-21 20:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a4c6d2e8f13"
down_revision: str | Sequence[str] | None = "7e3b2f1c9d55"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("parametres", sa.Column("version_regles", sa.Integer(), server_default="0", nullable=False))


def downgrade() -> None:
    op.drop_column("parametres", "version_regles")
