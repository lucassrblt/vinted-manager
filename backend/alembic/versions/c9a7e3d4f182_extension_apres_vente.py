"""extension Vinted : après-vente (récapitulatif quotidien, rappel avant la date limite)

Revision ID: c9a7e3d4f182
Revises: b8f2d5a1c463
Create Date: 2026-10-25 20:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9a7e3d4f182"
down_revision: str | Sequence[str] | None = "b8f2d5a1c463"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("compte_vinted", sa.Column("recap_envoye_le", sa.DateTime(timezone=True), nullable=True))
    op.add_column("parametres", sa.Column("recap_push_le", sa.DateTime(timezone=True), nullable=True))
    op.add_column("envoi", sa.Column("rappel_limite_le", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("envoi", "rappel_limite_le")
    op.drop_column("parametres", "recap_push_le")
    op.drop_column("compte_vinted", "recap_envoye_le")
