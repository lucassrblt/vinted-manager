from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, TimestampMixin, utcnow


class Utilisateur(TimestampMixin, Base):
    __tablename__ = "utilisateur"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True)
    mot_de_passe_hash: Mapped[str] = mapped_column(String(255))


class SessionUtilisateur(Base):
    __tablename__ = "session_utilisateur"

    id: Mapped[int] = mapped_column(primary_key=True)
    utilisateur_id: Mapped[int] = mapped_column(ForeignKey("utilisateur.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    expires_at: Mapped[datetime]
    user_agent: Mapped[str | None] = mapped_column(String(255))


class TentativeConnexion(Base):
    __tablename__ = "tentative_connexion"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), index=True)
    ip: Mapped[str | None] = mapped_column(String(64))
    date: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    succes: Mapped[bool]


class ModeleAnnonce(TimestampMixin, Base):
    __tablename__ = "modele_annonce"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(120))
    categorie: Mapped[str | None] = mapped_column(String(120))
    structure_titre: Mapped[str | None] = mapped_column(Text)
    structure_description: Mapped[str | None] = mapped_column(Text)
    mots_cles: Mapped[str | None] = mapped_column(Text)


class ModeleReponse(TimestampMixin, Base):
    __tablename__ = "modele_reponse"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(120))
    contexte: Mapped[str] = mapped_column(String(80))
    texte: Mapped[str] = mapped_column(Text)


class AbonnementPush(TimestampMixin, Base):
    __tablename__ = "abonnement_push"

    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(1000), unique=True)
    p256dh: Mapped[str] = mapped_column(String(255))
    auth: Mapped[str] = mapped_column(String(255))
    user_agent: Mapped[str | None] = mapped_column(String(255))


class Parametres(Base):
    """Une seule ligne (id=1)."""

    __tablename__ = "parametres"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    taux_cotisations: Mapped[Decimal] = mapped_column(Numeric(6, 4), default=Decimal("0.123"))
    coefficient_min: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("2"))
    coefficient_max: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("4"))
    seuil_article_lent_jours: Mapped[int] = mapped_column(default=7)
    objectif_ventes_jour: Mapped[int] = mapped_column(default=3)
    arrondi_seuil: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("30"))
    arrondi_pas: Mapped[Decimal] = mapped_column(Numeric(10, 2), default=Decimal("5"))
    imap_serveur: Mapped[str | None] = mapped_column(String(255))
    imap_port: Mapped[int | None]
    imap_email: Mapped[str | None] = mapped_column(String(255))
    imap_mot_de_passe_chiffre: Mapped[str | None] = mapped_column(Text)
    imap_dossier: Mapped[str] = mapped_column(String(255), default="INBOX")
    expediteurs_vinted: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["vinted.fr", "vinted.com"])
    derniere_synchro: Mapped[datetime | None]
    notifications: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {"vente": True, "litige": True, "offre": True, "rappel_envois": True},
    )
