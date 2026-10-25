"""extension Vinted : republication bloquée après un échec, report sans toucher à la date de publication

Revision ID: d2b6f9e0a571
Revises: c9a7e3d4f182
Create Date: 2026-10-25 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d2b6f9e0a571"
down_revision: str | Sequence[str] | None = "c9a7e3d4f182"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "article", sa.Column("republication_bloquee", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column(
        "article", sa.Column("republication_reportee_le", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("article", "republication_reportee_le")
    op.drop_column("article", "republication_bloquee")
