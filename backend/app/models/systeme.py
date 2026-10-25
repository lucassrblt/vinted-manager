from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, BigInteger, ForeignKey, Numeric, String, Text
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
    version_regles: Mapped[int] = mapped_column(default=0, server_default="0")
    expediteurs_vinted: Mapped[list[str]] = mapped_column(JSON, default=lambda: ["vinted.fr", "vinted.com"])
    # Photos IA : modèle par type de photo (None = choix par défaut du code), modèle « haute qualité »
    # utilisé par le bouton de régénération premium, et photo du fond (tapis) servant de référence.
    modeles_photos: Mapped[dict[str, str] | None] = mapped_column(JSON)
    modele_photos: Mapped[str] = mapped_column(String(120), default="google/nano-banana-2")
    photo_fond: Mapped[str | None] = mapped_column(String(500))
    notifications: Mapped[dict[str, Any]] = mapped_column(
        JSON,
        default=lambda: {"vente": True, "litige": True, "offre": True, "rappel_envois": True},
    )
    # Brouillons automatiques : la photo « devant » publiée est l'originale (redressée, recadrée).
    premiere_photo_reelle: Mapped[bool] = mapped_column(default=True, server_default="true")


class CompteVinted(TimestampMixin, Base):
    """Un compte Vinted, la boîte mail qui reçoit ses notifications (lue en IMAP, facultative)
    et l'extension Chrome qui agit sur Vinted pour lui."""

    __tablename__ = "compte_vinted"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(80))
    # Boîte mail : facultative (un compte peut n'être piloté que par l'extension).
    imap_serveur: Mapped[str | None] = mapped_column(String(255))
    imap_port: Mapped[int] = mapped_column(default=993)
    imap_email: Mapped[str | None] = mapped_column(String(255))
    imap_mot_de_passe_chiffre: Mapped[str | None] = mapped_column(Text)
    imap_dossier: Mapped[str] = mapped_column(String(255), default="INBOX")
    actif: Mapped[bool] = mapped_column(default=True)
    derniere_synchro: Mapped[datetime | None]
    # Extension : identifiant Vinted attendu (contrôle avant chaque lot d'actions), jeton hashé (SHA-256).
    vinted_user_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)
    # Dernier compte Vinted vu par l'extension dans le profil Chrome (à confirmer dans l'app).
    vinted_user_id_vu: Mapped[int | None] = mapped_column(BigInteger)
    vinted_login_vu: Mapped[str | None] = mapped_column(String(120))
    jeton_extension_hash: Mapped[str | None] = mapped_column(String(64), unique=True)
    extension_vue_le: Mapped[datetime | None]
    extension_version: Mapped[str | None] = mapped_column(String(40))
    telegram_chat_id: Mapped[str | None] = mapped_column(String(40))
    # Arrêt du compte : rien n'est exécuté sur Vinted, les tâches restent en file. Reprise manuelle.
    pause: Mapped[bool] = mapped_column(default=False, server_default="false")
    pause_raison: Mapped[str | None] = mapped_column(Text)
    # Réglages de l'automatisation (voir services/reglages.py pour les valeurs par défaut).
    reglages: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    @property
    def imap_configure(self) -> bool:
        return bool(self.imap_serveur and self.imap_email and self.imap_mot_de_passe_chiffre)


class JournalVinted(Base):
    """Ce que fait et observe l'extension : actions, erreurs Vinted, arrêts. Consultable dans l'app."""

    __tablename__ = "journal_vinted"

    id: Mapped[int] = mapped_column(primary_key=True)
    compte_id: Mapped[int | None] = mapped_column(
        ForeignKey("compte_vinted.id", ondelete="CASCADE"), index=True
    )
    date: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    niveau: Mapped[str] = mapped_column(String(10), default="info")  # info | alerte | erreur
    type: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    article_id: Mapped[int | None] = mapped_column(ForeignKey("article.id", ondelete="SET NULL"))
