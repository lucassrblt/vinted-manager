"""comptes vinted : plusieurs boîtes mail

Revision ID: 5c1d7e9a2b40
Revises: 88ae81bee805
Create Date: 2026-10-21 18:05:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5c1d7e9a2b40"
down_revision: str | Sequence[str] | None = "88ae81bee805"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compte_vinted",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("nom", sa.String(length=80), nullable=False),
        sa.Column("imap_serveur", sa.String(length=255), nullable=False),
        sa.Column("imap_port", sa.Integer(), nullable=False),
        sa.Column("imap_email", sa.String(length=255), nullable=False),
        sa.Column("imap_mot_de_passe_chiffre", sa.Text(), nullable=False),
        sa.Column("imap_dossier", sa.String(length=255), nullable=False),
        sa.Column("actif", sa.Boolean(), nullable=False),
        sa.Column("derniere_synchro", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for table, suppression in (
        ("email_vinted", "SET NULL"),
        ("article", "SET NULL"),
        ("sync_log", "CASCADE"),
    ):
        op.add_column(table, sa.Column("compte_id", sa.Integer(), nullable=True))
        op.create_foreign_key(
            f"fk_{table}_compte", table, "compte_vinted", ["compte_id"], ["id"], ondelete=suppression
        )
    op.create_index("ix_email_vinted_compte_id", "email_vinted", ["compte_id"])
    op.create_index("ix_article_compte_id", "article", ["compte_id"])

    # La boîte déjà configurée devient le premier compte ; ses mails lui sont rattachés.
    op.execute(
        """
        INSERT INTO compte_vinted (nom, imap_serveur, imap_port, imap_email, imap_mot_de_passe_chiffre,
                                   imap_dossier, actif, derniere_synchro, created_at)
        SELECT 'Compte 1', imap_serveur, COALESCE(imap_port, 993), imap_email, imap_mot_de_passe_chiffre,
               COALESCE(imap_dossier, 'INBOX'), true, derniere_synchro, now()
        FROM parametres
        WHERE imap_serveur IS NOT NULL AND imap_email IS NOT NULL AND imap_mot_de_passe_chiffre IS NOT NULL
        """
    )
    op.execute("UPDATE email_vinted SET compte_id = (SELECT min(id) FROM compte_vinted)")
    for colonne in ("imap_serveur", "imap_port", "imap_email", "imap_mot_de_passe_chiffre", "imap_dossier"):
        op.drop_column("parametres", colonne)
    op.drop_column("parametres", "derniere_synchro")


def downgrade() -> None:
    op.add_column("parametres", sa.Column("derniere_synchro", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "parametres", sa.Column("imap_dossier", sa.String(length=255), nullable=False, server_default="INBOX")
    )
    op.add_column("parametres", sa.Column("imap_mot_de_passe_chiffre", sa.Text(), nullable=True))
    op.add_column("parametres", sa.Column("imap_email", sa.String(length=255), nullable=True))
    op.add_column("parametres", sa.Column("imap_port", sa.Integer(), nullable=True))
    op.add_column("parametres", sa.Column("imap_serveur", sa.String(length=255), nullable=True))
    op.execute(
        """
        UPDATE parametres p SET imap_serveur = c.imap_serveur, imap_port = c.imap_port, imap_email = c.imap_email,
               imap_mot_de_passe_chiffre = c.imap_mot_de_passe_chiffre, imap_dossier = c.imap_dossier,
               derniere_synchro = c.derniere_synchro
        FROM (SELECT * FROM compte_vinted ORDER BY id LIMIT 1) c
        """
    )
    op.drop_index("ix_article_compte_id", table_name="article")
    op.drop_index("ix_email_vinted_compte_id", table_name="email_vinted")
    for table in ("sync_log", "article", "email_vinted"):
        op.drop_constraint(f"fk_{table}_compte", table, type_="foreignkey")
        op.drop_column(table, "compte_id")
    op.drop_table("compte_vinted")
