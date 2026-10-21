from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin
from app.models.enums import StatutEnvoi, StatutMessage, StatutTraitementEmail
from app.models.stock import Money


class RegleClassement(TimestampMixin, Base):
    __tablename__ = "regle_classement"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(120))
    type_cible: Mapped[str] = mapped_column(String(30))
    # {"expediteurs": [...], "sujet_contient": [...], "corps_regex": [...]}
    conditions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # {"prix": "regex", "titre_article": "regex", ...}
    extraction: Mapped[dict[str, str]] = mapped_column(JSON, default=dict)
    priorite: Mapped[int] = mapped_column(Integer, default=100)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class EmailVinted(TimestampMixin, Base):
    __tablename__ = "email_vinted"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[str] = mapped_column(String(500), unique=True)
    compte_id: Mapped[int | None] = mapped_column(
        ForeignKey("compte_vinted.id", ondelete="SET NULL"), index=True
    )
    date: Mapped[datetime | None]
    expediteur: Mapped[str | None] = mapped_column(String(255))
    sujet: Mapped[str | None] = mapped_column(String(500))
    corps_texte: Mapped[str | None] = mapped_column(Text)
    corps_html: Mapped[str | None] = mapped_column(Text)
    type_detecte: Mapped[str | None] = mapped_column(String(30), index=True)
    regle_id: Mapped[int | None] = mapped_column(ForeignKey("regle_classement.id", ondelete="SET NULL"))
    donnees_extraites: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    statut_traitement: Mapped[str] = mapped_column(
        String(20), default=StatutTraitementEmail.NOUVEAU, index=True
    )
    article_id: Mapped[int | None] = mapped_column(ForeignKey("article.id", ondelete="SET NULL"), index=True)
    vente_id: Mapped[int | None] = mapped_column(
        ForeignKey("vente.id", ondelete="SET NULL", use_alter=True, name="fk_email_vente")
    )


class PieceJointe(Base):
    __tablename__ = "piece_jointe"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("email_vinted.id", ondelete="CASCADE"), index=True)
    nom: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(100))
    chemin: Mapped[str] = mapped_column(String(500))


class Vente(TimestampMixin, Base):
    __tablename__ = "vente"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("article.id", ondelete="CASCADE"), index=True)
    prix: Mapped[Decimal] = mapped_column(Money)
    date_heure: Mapped[datetime]
    numero_commande: Mapped[str | None] = mapped_column(String(80))
    acheteur: Mapped[str | None] = mapped_column(String(120))
    frais: Mapped[Decimal | None] = mapped_column(Money)
    email_id: Mapped[int | None] = mapped_column(ForeignKey("email_vinted.id", ondelete="SET NULL"))
    auto_rapproche: Mapped[bool] = mapped_column(default=False)


class Envoi(TimestampMixin, Base):
    __tablename__ = "envoi"

    id: Mapped[int] = mapped_column(primary_key=True)
    vente_id: Mapped[int] = mapped_column(ForeignKey("vente.id", ondelete="CASCADE"), unique=True)
    transporteur: Mapped[str | None] = mapped_column(String(80))
    fichier_bordereau: Mapped[str | None] = mapped_column(String(500))
    lien_bordereau: Mapped[str | None] = mapped_column(String(1000))
    date_limite_envoi: Mapped[datetime | None]
    statut: Mapped[str] = mapped_column(String(20), default=StatutEnvoi.A_IMPRIMER, index=True)
    date_depot: Mapped[datetime | None]


class Message(TimestampMixin, Base):
    __tablename__ = "message"

    id: Mapped[int] = mapped_column(primary_key=True)
    email_id: Mapped[int | None] = mapped_column(ForeignKey("email_vinted.id", ondelete="CASCADE"))
    type: Mapped[str] = mapped_column(String(20))
    acheteur: Mapped[str | None] = mapped_column(String(120))
    article_id: Mapped[int | None] = mapped_column(ForeignKey("article.id", ondelete="SET NULL"), index=True)
    extrait: Mapped[str | None] = mapped_column(Text)
    montant_offre: Mapped[Decimal | None] = mapped_column(Money)
    reponse_suggeree: Mapped[str | None] = mapped_column(Text)
    reponse_finale: Mapped[str | None] = mapped_column(Text)
    statut: Mapped[str] = mapped_column(String(20), default=StatutMessage.A_TRAITER, index=True)


class SyncLog(Base):
    __tablename__ = "sync_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    debut: Mapped[datetime]
    fin: Mapped[datetime | None]
    nb_mails: Mapped[int] = mapped_column(default=0)
    erreur: Mapped[str | None] = mapped_column(Text)
    compte_id: Mapped[int | None] = mapped_column(ForeignKey("compte_vinted.id", ondelete="CASCADE"))
