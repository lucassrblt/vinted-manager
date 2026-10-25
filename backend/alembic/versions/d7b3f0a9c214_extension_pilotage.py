"""extension Vinted : file de tâches, Telegram, surveillance, interrupteur global

Revision ID: d7b3f0a9c214
Revises: c4a1e7d2f950
Create Date: 2026-10-25 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d7b3f0a9c214"
down_revision: str | Sequence[str] | None = "c4a1e7d2f950"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "parametres", sa.Column("automatisation_active", sa.Boolean(), server_default="true", nullable=False)
    )
    op.add_column(
        "parametres", sa.Column("telegram_offset", sa.BigInteger(), server_default="0", nullable=False)
    )
    op.add_column("parametres", sa.Column("telegram_attente", sa.JSON(), nullable=True))
    op.add_column("compte_vinted", sa.Column("telegram_code", sa.String(length=6), nullable=True))
    op.add_column(
        "compte_vinted", sa.Column("telegram_code_expire_le", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "compte_vinted", sa.Column("onglet_ferme_depuis", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "compte_vinted", sa.Column("alerte_hors_ligne_le", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("compte_vinted", sa.Column("alerte_onglet_le", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "tache_vinted",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("compte_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=30), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("priorite", sa.Integer(), nullable=False),
        sa.Column("executer_apres", sa.DateTime(timezone=True), nullable=False),
        sa.Column("statut", sa.String(length=20), nullable=False),
        sa.Column("resultat", sa.JSON(), nullable=True),
        sa.Column("erreur", sa.Text(), nullable=True),
        sa.Column("erreur_vinted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("tentatives", sa.Integer(), nullable=False),
        sa.Column("cle", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("debut_le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fin_le", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["compte_id"], ["compte_vinted.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["article_id"], ["article.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for colonne in ("compte_id", "article_id", "executer_apres", "statut", "cle"):
        op.create_index(f"ix_tache_vinted_{colonne}", "tache_vinted", [colonne])


def downgrade() -> None:
    op.drop_table("tache_vinted")
    for colonne in (
        "alerte_onglet_le",
        "alerte_hors_ligne_le",
        "onglet_ferme_depuis",
        "telegram_code_expire_le",
        "telegram_code",
    ):
        op.drop_column("compte_vinted", colonne)
    for colonne in ("telegram_attente", "telegram_offset", "automatisation_active"):
        op.drop_column("parametres", colonne)
