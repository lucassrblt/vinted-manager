"""extension Vinted : conversations suivies par l'assistant, lecture du dressing

Revision ID: e1c5a8b3d702
Revises: d7b3f0a9c214
Create Date: 2026-10-25 16:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e1c5a8b3d702"
down_revision: str | Sequence[str] | None = "d7b3f0a9c214"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "compte_vinted", sa.Column("inbox_initialise_le", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("article", sa.Column("vinted_photos", sa.JSON(), nullable=True))
    op.add_column("article", sa.Column("vinted_vues", sa.Integer(), nullable=True))
    op.add_column("article", sa.Column("vinted_favoris", sa.Integer(), nullable=True))
    op.add_column("article", sa.Column("vinted_vu_le", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "conversation_vinted",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("compte_id", sa.Integer(), nullable=False),
        sa.Column("article_id", sa.Integer(), nullable=True),
        sa.Column("vinted_item_ids", sa.JSON(), nullable=True),
        sa.Column("transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("interlocuteur_id", sa.BigInteger(), nullable=True),
        sa.Column("interlocuteur_login", sa.String(length=120), nullable=True),
        sa.Column("dernier_message_le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("dernier_traite_le", sa.DateTime(timezone=True), nullable=True),
        sa.Column("messages_vus", sa.JSON(), nullable=True),
        sa.Column("dernier_propose", sa.Numeric(10, 2), nullable=True),
        sa.Column("plancher_renvoye", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["compte_id"], ["compte_vinted.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["article_id"], ["article.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversation_vinted_compte_id", "conversation_vinted", ["compte_id"])
    op.create_index("ix_conversation_vinted_article_id", "conversation_vinted", ["article_id"])
    op.create_index(
        "ix_conversation_vinted_dernier_message_le", "conversation_vinted", ["dernier_message_le"]
    )


def downgrade() -> None:
    op.drop_table("conversation_vinted")
    for colonne in ("vinted_vu_le", "vinted_favoris", "vinted_vues", "vinted_photos"):
        op.drop_column("article", colonne)
    op.drop_column("compte_vinted", "inbox_initialise_le")
