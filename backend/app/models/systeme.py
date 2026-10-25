from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, BigInteger, ForeignKey, Numeric, String, Text, UniqueConstraint
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
    # Interrupteur global de l'automatisation Vinted (arrêt d'urgence de tous les comptes).
    automatisation_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    # Telegram : dernier update lu (long polling) et réponses en cours de modification par chat.
    telegram_offset: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    telegram_attente: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Récapitulatif des colis en notification push (sans Telegram) : dernier envoi.
    recap_push_le: Mapped[datetime | None]


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
    # Appairage Telegram : code à 6 chiffres envoyé au bot avec /start.
    telegram_code: Mapped[str | None] = mapped_column(String(6))
    telegram_code_expire_le: Mapped[datetime | None]
    # Surveillance : alertes « hors ligne » et « onglet fermé » déjà envoyées (une seule fois).
    onglet_ferme_depuis: Mapped[datetime | None]
    # Première lecture de la messagerie : rien d'antérieur n'est traité par l'assistant.
    inbox_initialise_le: Mapped[datetime | None]
    # Notifications Vinted déjà vues (identifiants récents) ; None tant que la première lecture n'a pas eu lieu.
    notifications_vues: Mapped[list[str] | None] = mapped_column(JSON)
    notifications_format_alerte_le: Mapped[datetime | None]
    # Récapitulatif quotidien des colis (Telegram) : dernier envoi.
    recap_envoye_le: Mapped[datetime | None]
    alerte_hors_ligne_le: Mapped[datetime | None]
    alerte_onglet_le: Mapped[datetime | None]

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


class TacheVinted(Base):
    """Une action à exécuter sur Vinted par l'extension. Le backend décide, l'extension exécute.

    Statuts : a_valider (attend Lucas, sur Telegram) | a_faire | en_cours | faite | erreur | annulee.
    Une tâche en erreur n'est jamais relancée automatiquement.
    """

    __tablename__ = "tache_vinted"

    id: Mapped[int] = mapped_column(primary_key=True)
    compte_id: Mapped[int] = mapped_column(ForeignKey("compte_vinted.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(30))
    article_id: Mapped[int | None] = mapped_column(ForeignKey("article.id", ondelete="SET NULL"), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    priorite: Mapped[int] = mapped_column(default=5)
    executer_apres: Mapped[datetime] = mapped_column(default=utcnow, index=True)
    statut: Mapped[str] = mapped_column(String(20), default="a_faire", index=True)
    resultat: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    erreur: Mapped[str | None] = mapped_column(Text)
    # Échec renvoyé par Vinted (et non un contrôle préalable) : compte pour les 3 erreurs consécutives.
    erreur_vinted: Mapped[bool] = mapped_column(default=False, server_default="false")
    tentatives: Mapped[int] = mapped_column(default=0)
    # Empêche de créer deux fois la même action (ex. « offre:<id de la demande> »).
    cle: Mapped[str | None] = mapped_column(String(120), index=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    debut_le: Mapped[datetime | None]
    fin_le: Mapped[datetime | None]


class ConversationVinted(Base):
    """Conversation de la messagerie Vinted suivie par l'assistant, avec son point de reprise."""

    __tablename__ = "conversation_vinted"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # UUID Vinted
    compte_id: Mapped[int] = mapped_column(ForeignKey("compte_vinted.id", ondelete="CASCADE"), index=True)
    article_id: Mapped[int | None] = mapped_column(ForeignKey("article.id", ondelete="SET NULL"), index=True)
    vinted_item_ids: Mapped[list[int] | None] = mapped_column(JSON)
    transaction_id: Mapped[int | None] = mapped_column(BigInteger)
    interlocuteur_id: Mapped[int | None] = mapped_column(BigInteger)
    interlocuteur_login: Mapped[str | None] = mapped_column(String(120))
    # Dernier message échangé (dans un sens ou dans l'autre) : la republication attend 1 h après.
    dernier_message_le: Mapped[datetime | None] = mapped_column(index=True)
    # Point de reprise : messages traités jusqu'à cette date, et leurs identifiants (jamais deux fois).
    dernier_traite_le: Mapped[datetime | None]
    messages_vus: Mapped[list[str] | None] = mapped_column(JSON)
    # Négociation : dernière contre-offre envoyée, et plancher déjà renvoyé une fois.
    dernier_propose: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    plancher_renvoye: Mapped[bool] = mapped_column(default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class FavoriVinted(Base):
    """Un membre a mis une annonce en favori. Un seul message et une seule offre par membre et par article."""

    __tablename__ = "favori_vinted"
    __table_args__ = (
        UniqueConstraint("compte_id", "vinted_item_id", "membre_id", name="uq_favori_membre_article"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    compte_id: Mapped[int] = mapped_column(ForeignKey("compte_vinted.id", ondelete="CASCADE"), index=True)
    article_id: Mapped[int | None] = mapped_column(ForeignKey("article.id", ondelete="SET NULL"), index=True)
    vinted_item_id: Mapped[int] = mapped_column(BigInteger, index=True)
    membre_id: Mapped[int] = mapped_column(BigInteger)
    membre_login: Mapped[str | None] = mapped_column(String(120))
    notification_id: Mapped[str | None] = mapped_column(String(80))
    recu_le: Mapped[datetime]
    # a_relancer | programme | relance | ignore | erreur
    statut: Mapped[str] = mapped_column(String(20), default="a_relancer")
    raison: Mapped[str | None] = mapped_column(Text)
    offre_envoyee: Mapped[bool] = mapped_column(default=False, server_default="false")
    montant_offre: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    tache_id: Mapped[int | None] = mapped_column(ForeignKey("tache_vinted.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
