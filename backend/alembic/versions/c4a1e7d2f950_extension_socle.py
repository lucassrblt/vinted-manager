"""extension Vinted : comptes pilotés, suivi des brouillons, contrôle de couleur, journal

Revision ID: c4a1e7d2f950
Revises: b2e8f4a61c07
Create Date: 2026-10-25 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4a1e7d2f950"
down_revision: str | Sequence[str] | None = "b2e8f4a61c07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Boîte mail facultative : un compte peut n'être piloté que par l'extension.
    for colonne in ("imap_serveur", "imap_email", "imap_mot_de_passe_chiffre"):
        op.alter_column("compte_vinted", colonne, nullable=True)
    op.add_column("compte_vinted", sa.Column("vinted_user_id", sa.BigInteger(), nullable=True))
    op.add_column("compte_vinted", sa.Column("vinted_user_id_vu", sa.BigInteger(), nullable=True))
    op.add_column("compte_vinted", sa.Column("vinted_login_vu", sa.String(length=120), nullable=True))
    op.add_column("compte_vinted", sa.Column("jeton_extension_hash", sa.String(length=64), nullable=True))
    op.add_column("compte_vinted", sa.Column("extension_vue_le", sa.DateTime(timezone=True), nullable=True))
    op.add_column("compte_vinted", sa.Column("extension_version", sa.String(length=40), nullable=True))
    op.add_column("compte_vinted", sa.Column("telegram_chat_id", sa.String(length=40), nullable=True))
    op.add_column("compte_vinted", sa.Column("pause", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("compte_vinted", sa.Column("pause_raison", sa.Text(), nullable=True))
    op.add_column("compte_vinted", sa.Column("reglages", sa.JSON(), nullable=True))
    op.create_unique_constraint("uq_compte_vinted_user_id", "compte_vinted", ["vinted_user_id"])
    op.create_unique_constraint("uq_compte_jeton_extension", "compte_vinted", ["jeton_extension_hash"])

    op.add_column("article", sa.Column("vinted_item_id", sa.BigInteger(), nullable=True))
    op.add_column("article", sa.Column("vinted_draft_id", sa.BigInteger(), nullable=True))
    op.add_column("article", sa.Column("brouillon_statut", sa.String(length=20), nullable=True))
    op.add_column("article", sa.Column("brouillon_erreur", sa.Text(), nullable=True))
    op.add_column("article", sa.Column("brouillon_cree_le", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "article", sa.Column("couleur_a_verifier", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column("article", sa.Column("ai_photo_declare", sa.Boolean(), nullable=True))
    op.add_column("article", sa.Column("prix_initial", sa.Numeric(10, 2), nullable=True))
    op.add_column("article", sa.Column("prix_plancher", sa.Numeric(10, 2), nullable=True))
    op.add_column(
        "article", sa.Column("importe_vinted", sa.Boolean(), server_default="false", nullable=False)
    )
    op.create_index("ix_article_vinted_item_id", "article", ["vinted_item_id"])
    op.create_index("ix_article_vinted_draft_id", "article", ["vinted_draft_id"])

    op.add_column("photo_article", sa.Column("ecart_couleur", sa.Float(), nullable=True))
    op.add_column(
        "photo_article", sa.Column("couleur_validee", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column(
        "parametres", sa.Column("premiere_photo_reelle", sa.Boolean(), server_default="true", nullable=False)
    )

    op.create_table(
        "journal_vinted",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("compte_id", sa.Integer(), nullable=True),
        sa.Column("date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("niveau", sa.String(length=10), nullable=False),
        sa.Column("type", sa.String(length=40), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["compte_id"], ["compte_vinted.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["article_id"], ["article.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_journal_vinted_compte_id", "journal_vinted", ["compte_id"])
    op.create_index("ix_journal_vinted_date", "journal_vinted", ["date"])


def downgrade() -> None:
    op.drop_table("journal_vinted")
    op.drop_column("parametres", "premiere_photo_reelle")
    op.drop_column("photo_article", "couleur_validee")
    op.drop_column("photo_article", "ecart_couleur")
    op.drop_index("ix_article_vinted_draft_id", "article")
    op.drop_index("ix_article_vinted_item_id", "article")
    for colonne in (
        "importe_vinted",
        "prix_plancher",
        "prix_initial",
        "ai_photo_declare",
        "couleur_a_verifier",
        "brouillon_cree_le",
        "brouillon_erreur",
        "brouillon_statut",
        "vinted_draft_id",
        "vinted_item_id",
    ):
        op.drop_column("article", colonne)
    op.drop_constraint("uq_compte_jeton_extension", "compte_vinted")
    op.drop_constraint("uq_compte_vinted_user_id", "compte_vinted")
    for colonne in (
        "reglages",
        "pause_raison",
        "pause",
        "telegram_chat_id",
        "extension_version",
        "extension_vue_le",
        "jeton_extension_hash",
        "vinted_login_vu",
        "vinted_user_id_vu",
        "vinted_user_id",
    ):
        op.drop_column("compte_vinted", colonne)
    for colonne in ("imap_serveur", "imap_email", "imap_mot_de_passe_chiffre"):
        op.alter_column("compte_vinted", colonne, nullable=False)
