from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, BigInteger, CheckConstraint, ForeignKey, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base, TimestampMixin, utcnow
from app.models.enums import StatutArticle

Money = Numeric(10, 2)


class Batch(TimestampMixin, Base):
    __tablename__ = "batch"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(120), unique=True)
    fournisseur: Mapped[str | None] = mapped_column(String(120))
    date_commande: Mapped[date | None]
    total_paye: Mapped[Decimal | None] = mapped_column(Money)
    remise_globale: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    notes: Mapped[str | None] = mapped_column(Text)

    articles: Mapped[list["Article"]] = relationship(back_populates="batch")


class Article(TimestampMixin, Base):
    __tablename__ = "article"

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(255))
    marque: Mapped[str | None] = mapped_column(String(120), index=True)
    categorie: Mapped[str | None] = mapped_column(String(120), index=True)
    taille: Mapped[str | None] = mapped_column(String(40))
    couleur: Mapped[str | None] = mapped_column(String(80))
    etat: Mapped[str | None] = mapped_column(String(40))
    prix_achat_brut: Mapped[Decimal | None] = mapped_column(Money)
    remise: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    prix_achat_net: Mapped[Decimal | None] = mapped_column(Money)
    prix_vente_cible: Mapped[Decimal | None] = mapped_column(Money)
    prix_vente_reel: Mapped[Decimal | None] = mapped_column(Money)
    statut: Mapped[str] = mapped_column(String(30), default=StatutArticle.RECU_A_PUBLIER, index=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batch.id", ondelete="SET NULL"), index=True)
    # Compte Vinted sur lequel l'article est en vente (None = pas encore attribué)
    compte_id: Mapped[int | None] = mapped_column(
        ForeignKey("compte_vinted.id", ondelete="SET NULL"), index=True
    )
    source: Mapped[str | None] = mapped_column(String(120))
    # Pièce perso (revente de ses propres affaires) : coût d'achat 0 €, hors batchs
    perso: Mapped[bool] = mapped_column(default=False, server_default="false")
    date_achat: Mapped[date | None]
    date_reception: Mapped[datetime | None]
    date_publication: Mapped[datetime | None]
    date_vente: Mapped[datetime | None]
    date_envoi: Mapped[datetime | None]
    date_livraison: Mapped[datetime | None]
    litige: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str | None] = mapped_column(Text)
    # Fiche annonce (étape 3)
    modele: Mapped[str | None] = mapped_column(String(120))
    matiere: Mapped[str | None] = mapped_column(String(120))
    defauts: Mapped[str | None] = mapped_column(Text)
    titre_annonce: Mapped[str | None] = mapped_column(String(120))
    description_annonce: Mapped[str | None] = mapped_column(Text)
    mots_cles_annonce: Mapped[str | None] = mapped_column(Text)
    mesures: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    # Vinted (extension) : annonce et brouillon, prix de référence pour les offres.
    vinted_item_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    vinted_draft_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    brouillon_statut: Mapped[str | None] = mapped_column(String(20))  # a_creer | en_cours | cree | erreur
    brouillon_erreur: Mapped[str | None] = mapped_column(Text)
    brouillon_cree_le: Mapped[datetime | None]
    # Brouillon bloqué tant qu'une photo retouchée a une couleur trop éloignée de l'original.
    couleur_a_verifier: Mapped[bool] = mapped_column(default=False, server_default="false")
    ai_photo_declare: Mapped[bool | None]
    prix_initial: Mapped[Decimal | None] = mapped_column(Money)  # première publication ou import
    prix_plancher: Mapped[Decimal | None] = mapped_column(Money)  # 82 % du prix initial
    importe_vinted: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Dernière lecture du dressing Vinted : photos publiées (URL), vues, favoris.
    vinted_photos: Mapped[list[str] | None] = mapped_column(JSON)
    vinted_vues: Mapped[int | None]
    vinted_favoris: Mapped[int | None]
    vinted_vu_le: Mapped[datetime | None]
    # Republication : date de la dernière mise en ligne et nombre de republications.
    derniere_publication_le: Mapped[datetime | None]
    republications: Mapped[int] = mapped_column(default=0, server_default="0")
    # Republication en échec : plus aucune republication automatique tant que Lucas n'a pas vérifié.
    republication_bloquee: Mapped[bool] = mapped_column(default=False, server_default="false")
    # Republication impossible (fiche incomplète) : prochain examen à la prochaine échéance.
    republication_reportee_le: Mapped[datetime | None]
    # Baisse de prix automatique : une seule fois par article (date, même si aucune baisse n'était possible).
    baisse_prix_le: Mapped[datetime | None]
    prix_avant_baisse: Mapped[Decimal | None] = mapped_column(Money)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    batch: Mapped[Batch | None] = relationship(back_populates="articles")
    historique: Mapped[list["HistoriqueStatut"]] = relationship(
        back_populates="article", cascade="all, delete-orphan", order_by="HistoriqueStatut.date"
    )


class HistoriqueStatut(Base):
    __tablename__ = "historique_statut"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("article.id", ondelete="CASCADE"), index=True)
    ancien_statut: Mapped[str | None] = mapped_column(String(30))
    nouveau_statut: Mapped[str] = mapped_column(String(30))
    date: Mapped[datetime] = mapped_column(default=utcnow)
    commentaire: Mapped[str | None] = mapped_column(String(255))

    article: Mapped[Article] = relationship(back_populates="historique")


class PreuveAchat(Base):
    __tablename__ = "preuve_achat"
    __table_args__ = (CheckConstraint("article_id IS NOT NULL OR batch_id IS NOT NULL", name="preuve_cible"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int | None] = mapped_column(ForeignKey("article.id", ondelete="CASCADE"), index=True)
    batch_id: Mapped[int | None] = mapped_column(ForeignKey("batch.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(30))
    fichier: Mapped[str] = mapped_column(String(500))
    nom_original: Mapped[str] = mapped_column(String(255))
    mime: Mapped[str] = mapped_column(String(100))
    taille_octets: Mapped[int]
    date_upload: Mapped[datetime] = mapped_column(default=utcnow)
    note: Mapped[str | None] = mapped_column(String(500))


class PisteSourcing(TimestampMixin, Base):
    __tablename__ = "piste_sourcing"

    id: Mapped[int] = mapped_column(primary_key=True)
    origine: Mapped[str] = mapped_column(String(30), default="manuel")  # tests / recherche / manuel
    marque: Mapped[str | None] = mapped_column(String(120))
    produit: Mapped[str] = mapped_column(String(255))
    mots_cles: Mapped[str | None] = mapped_column(Text)
    categorie: Mapped[str | None] = mapped_column(String(120))
    achat_max: Mapped[Decimal | None] = mapped_column(Money)
    revente_basse: Mapped[Decimal | None] = mapped_column(Money)
    revente_haute: Mapped[Decimal | None] = mapped_column(Money)
    priorite: Mapped[str | None] = mapped_column(String(30))
    quantite_test: Mapped[str | None] = mapped_column(String(30))
    commentaire: Mapped[str | None] = mapped_column(Text)


class PhotoArticle(TimestampMixin, Base):
    """Photo d'un article : l'original déposé et, sauf pour un défaut, sa version retouchée par l'IA."""

    __tablename__ = "photo_article"

    id: Mapped[int] = mapped_column(primary_key=True)
    article_id: Mapped[int] = mapped_column(ForeignKey("article.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(20))  # devant | dos | etiquette | logo | detail | defaut
    ordre: Mapped[int] = mapped_column(default=0)
    fichier_original: Mapped[str] = mapped_column(String(500))
    fichier_genere: Mapped[str | None] = mapped_column(String(500))
    # a_generer | en_cours | genere | erreur | original (défaut : jamais retouché)
    statut: Mapped[str] = mapped_column(String(20), default="a_generer")
    version_choisie: Mapped[str] = mapped_column(String(10), default="genere")  # genere | original
    modele: Mapped[str | None] = mapped_column(String(120))
    disposition: Mapped[str | None] = mapped_column(Text)
    prediction_id: Mapped[str | None] = mapped_column(String(80))
    nb_generations: Mapped[int] = mapped_column(default=0)
    cout_estime: Mapped[Decimal] = mapped_column(
        Numeric(10, 4), default=Decimal("0")
    )  # USD, prix à 3 décimales
    erreur: Mapped[str | None] = mapped_column(Text)
    # Contrôle de couleur (ΔE CIE76 entre l'original et la version retouchée, zone centrale).
    ecart_couleur: Mapped[float | None]
    couleur_validee: Mapped[bool] = mapped_column(default=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)


class PhotoVariante(TimestampMixin, Base):
    """Résultat d'un modèle pour une photo, lors d'une comparaison de modèles."""

    __tablename__ = "photo_variante"

    id: Mapped[int] = mapped_column(primary_key=True)
    photo_id: Mapped[int] = mapped_column(ForeignKey("photo_article.id", ondelete="CASCADE"), index=True)
    modele: Mapped[str] = mapped_column(String(120))
    statut: Mapped[str] = mapped_column(String(20), default="en_cours")  # en_cours | genere | erreur
    fichier: Mapped[str | None] = mapped_column(String(500))
    disposition: Mapped[str | None] = mapped_column(Text)
    cout_estime: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"))
    duree_secondes: Mapped[float | None]
    erreur: Mapped[str | None] = mapped_column(Text)
