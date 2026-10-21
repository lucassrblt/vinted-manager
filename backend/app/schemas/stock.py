from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.db import utcnow
from app.models import Article, Parametres
from app.models.enums import STATUTS_VENDUS, EtatArticle, StatutArticle
from app.services import calculs


class ArticleBase(BaseModel):
    nom: str = Field(min_length=1, max_length=255)
    marque: str | None = None
    categorie: str | None = None
    taille: str | None = None
    couleur: str | None = None
    etat: EtatArticle | None = None
    prix_achat_brut: Decimal | None = Field(default=None, ge=0)
    remise: Decimal = Field(default=Decimal("0"), ge=0)
    prix_vente_cible: Decimal | None = Field(default=None, ge=0)
    prix_vente_reel: Decimal | None = Field(default=None, ge=0)
    batch_id: int | None = None
    source: str | None = None
    date_achat: date | None = None
    notes: str | None = None
    mesures: dict[str, Any] | None = None


class ArticleCreate(ArticleBase):
    prix_achat_net: Decimal | None = Field(default=None, ge=0)
    statut: StatutArticle = StatutArticle.RECU_A_PUBLIER


class ArticleUpdate(BaseModel):
    """Tous les champs optionnels : seuls ceux envoyés sont modifiés."""

    nom: str | None = Field(default=None, min_length=1, max_length=255)
    marque: str | None = None
    categorie: str | None = None
    taille: str | None = None
    couleur: str | None = None
    etat: EtatArticle | None = None
    prix_achat_brut: Decimal | None = Field(default=None, ge=0)
    remise: Decimal | None = Field(default=None, ge=0)
    prix_achat_net: Decimal | None = Field(default=None, ge=0)
    prix_vente_cible: Decimal | None = Field(default=None, ge=0)
    prix_vente_reel: Decimal | None = Field(default=None, ge=0)
    batch_id: int | None = None
    source: str | None = None
    date_achat: date | None = None
    date_publication: datetime | None = None
    date_vente: datetime | None = None
    notes: str | None = None
    titre_annonce: str | None = None
    description_annonce: str | None = None
    mots_cles_annonce: str | None = None
    modele: str | None = None
    matiere: str | None = None
    defauts: str | None = None
    mesures: dict[str, Any] | None = None


class ArticleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nom: str
    marque: str | None
    categorie: str | None
    taille: str | None
    couleur: str | None
    etat: str | None
    prix_achat_brut: Decimal | None
    remise: Decimal
    prix_achat_net: Decimal | None
    prix_vente_cible: Decimal | None
    prix_vente_reel: Decimal | None
    statut: StatutArticle
    batch_id: int | None
    batch_nom: str | None = None
    source: str | None
    date_achat: date | None
    date_reception: datetime | None
    date_publication: datetime | None
    date_vente: datetime | None
    date_envoi: datetime | None
    date_livraison: datetime | None
    litige: bool
    notes: str | None
    titre_annonce: str | None
    description_annonce: str | None
    mots_cles_annonce: str | None
    modele: str | None
    matiere: str | None
    defauts: str | None
    mesures: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime
    # Champs calculés
    prix_vente: Decimal | None = None
    marge: Decimal | None = None
    marge_pct: Decimal | None = None
    coefficient: Decimal | None = None
    indicateur: str | None = None
    jours_en_ligne: int | None = None
    delai_vente_heures: float | None = None


def prix_vente_effectif(a: Article) -> Decimal | None:
    """Prix réel si l'article est vendu, sinon prix cible (comme la colonne « Prix de vente » de l'Excel)."""
    return a.prix_vente_reel if a.prix_vente_reel is not None else a.prix_vente_cible


def vers_out(a: Article, params: Parametres | None = None) -> ArticleOut:
    out = ArticleOut.model_validate(a)
    out.batch_nom = a.batch.nom if a.batch else None
    pv = prix_vente_effectif(a)
    out.prix_vente = pv
    out.marge = calculs.marge_nette(pv, a.prix_achat_net)
    out.marge_pct = calculs.marge_pct(pv, a.prix_achat_net)
    out.coefficient = calculs.coefficient(pv, a.prix_achat_net)
    ind = (
        calculs.indicateur(out.coefficient, params.coefficient_min, params.coefficient_max)
        if params
        else calculs.indicateur(out.coefficient)
    )
    out.indicateur = ind.value if ind else None
    if a.date_publication:
        fin = a.date_vente if a.statut in STATUTS_VENDUS and a.date_vente else utcnow()
        out.jours_en_ligne = max(0, (fin - a.date_publication).days)
    out.delai_vente_heures = calculs.delai_vente_heures(a.date_publication, a.date_vente)
    return out


class Page[T](BaseModel):
    items: list[T]
    total: int
    page: int
    taille_page: int


class HistoriqueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ancien_statut: str | None
    nouveau_statut: str
    date: datetime
    commentaire: str | None


class ChangementStatut(BaseModel):
    statut: StatutArticle
    date: datetime | None = None
    commentaire: str | None = None


class ActionGroupee(BaseModel):
    ids: list[int] = Field(min_length=1, max_length=500)
    action: str  # statut | publie_aujourdhui | batch | supprimer
    statut: StatutArticle | None = None
    batch_id: int | None = None


class BatchArticleIn(BaseModel):
    nom: str = Field(min_length=1, max_length=255)
    taille: str | None = None
    couleur: str | None = None
    marque: str | None = None
    categorie: str | None = None
    prix_achat_brut: Decimal = Field(ge=0)
    prix_vente_cible: Decimal | None = Field(default=None, ge=0)
    quantite: int = Field(default=1, ge=1, le=50)


class BatchCreate(BaseModel):
    nom: str = Field(min_length=1, max_length=120)
    fournisseur: str | None = None
    date_commande: date | None = None
    total_paye: Decimal | None = Field(default=None, ge=0)
    remise_globale: Decimal = Field(default=Decimal("0"), ge=0)
    notes: str | None = None
    statut_articles: StatutArticle = StatutArticle.COMMANDE
    articles: list[BatchArticleIn] = Field(default_factory=list)


class BatchUpdate(BaseModel):
    nom: str | None = Field(default=None, min_length=1, max_length=120)
    fournisseur: str | None = None
    date_commande: date | None = None
    total_paye: Decimal | None = Field(default=None, ge=0)
    notes: str | None = None


class BatchStats(BaseModel):
    id: int
    nom: str
    fournisseur: str | None
    date_commande: date | None
    total_paye: Decimal | None
    remise_globale: Decimal
    notes: str | None
    nb_articles: int
    nb_publies: int
    nb_vendus: int
    sell_through: Decimal | None
    ca: Decimal
    marge_realisee: Decimal
    coefficient_ventes: Decimal | None
    delai_moyen_heures: float | None
    valeur_stock_restant: Decimal
    investi: Decimal


class PreuveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    article_id: int | None
    batch_id: int | None
    type: str
    nom_original: str
    mime: str
    taille_octets: int
    date_upload: datetime
    note: str | None


class PisteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    origine: str
    marque: str | None
    produit: str
    mots_cles: str | None
    categorie: str | None
    achat_max: Decimal | None
    revente_basse: Decimal | None
    revente_haute: Decimal | None
    priorite: str | None
    quantite_test: str | None
    commentaire: str | None
    # Performances réelles de la même marque / catégorie dans l'historique
    perf_nb_ventes: int = 0
    perf_prix_moyen: Decimal | None = None
    perf_delai_moyen_jours: float | None = None
    perf_coefficient_moyen: Decimal | None = None
    perf_base: str | None = None  # "marque+categorie" | "marque" | "categorie"


class PisteIn(BaseModel):
    marque: str | None = None
    produit: str = Field(min_length=1, max_length=255)
    mots_cles: str | None = None
    categorie: str | None = None
    achat_max: Decimal | None = Field(default=None, ge=0)
    revente_basse: Decimal | None = Field(default=None, ge=0)
    revente_haute: Decimal | None = Field(default=None, ge=0)
    priorite: str | None = None
    quantite_test: str | None = None
    commentaire: str | None = None


class PisteUpdate(BaseModel):
    marque: str | None = None
    produit: str | None = Field(default=None, min_length=1, max_length=255)
    mots_cles: str | None = None
    categorie: str | None = None
    achat_max: Decimal | None = Field(default=None, ge=0)
    revente_basse: Decimal | None = Field(default=None, ge=0)
    revente_haute: Decimal | None = Field(default=None, ge=0)
    priorite: str | None = None
    quantite_test: str | None = None
    commentaire: str | None = None
