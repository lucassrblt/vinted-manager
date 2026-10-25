"""extension Vinted : favoris (message et offre aux membres)

Revision ID: f3d9b2c6e815
Revises: e1c5a8b3d702
Create Date: 2026-10-25 17:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3d9b2c6e815"
down_revision: str | Sequence[str] | None = "e1c5a8b3d702"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("compte_vinted", sa.Column("notifications_vues", sa.JSON(), nullable=True))
    op.add_column(
        "compte_vinted",
        sa.Column("notifications_format_alerte_le", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "favori_vinted",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("compte_id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=True),
        sa.Column("vinted_item_id", sa.BigInteger(), nullable=False),
        sa.Column("membre_id", sa.BigInteger(), nullable=False),
        sa.Column("membre_login", sa.String(length=120), nullable=True),
        sa.Column("notification_id", sa.String(length=80), nullable=True),
        sa.Column("recu_le", sa.DateTime(timezone=True), nullable=False),
        sa.Column("statut", sa.String(length=20), nullable=False),
        sa.Column("raison", sa.Text(), nullable=True),
        sa.Column("offre_envoyee", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("montant_offre", sa.Numeric(10, 2), nullable=True),
        sa.Column("tache_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["compte_id"], ["compte_vinted.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["article_id"], ["article.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tache_id"], ["tache_vinted.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("compte_id", "vinted_item_id", "membre_id", name="uq_favori_membre_article"),
    )
    op.create_index("ix_favori_vinted_compte_id", "favori_vinted", ["compte_id"])
    op.create_index("ix_favori_vinted_article_id", "favori_vinted", ["article_id"])
    op.create_index("ix_favori_vinted_vinted_item_id", "favori_vinted", ["vinted_item_id"])


def downgrade() -> None:
    op.drop_table("favori_vinted")
    op.drop_column("compte_vinted", "notifications_format_alerte_le")
    op.drop_column("compte_vinted", "notifications_vues")
