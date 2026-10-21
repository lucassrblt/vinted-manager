"""Paramètres, recherche globale, écran du jour (version étape 1) et alertes."""

from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select

from app.api.deps import Db, get_parametres
from app.db import utcnow
from app.models import Article, Batch
from app.models.enums import StatutArticle
from app.services import stats

router = APIRouter(tags=["systeme"])


class ParametresOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    taux_cotisations: Decimal
    coefficient_min: Decimal
    coefficient_max: Decimal
    seuil_article_lent_jours: int
    objectif_ventes_jour: int
    arrondi_seuil: Decimal
    arrondi_pas: Decimal


class ParametresUpdate(BaseModel):
    taux_cotisations: Decimal | None = Field(default=None, ge=0, le=1)
    coefficient_min: Decimal | None = Field(default=None, gt=0)
    coefficient_max: Decimal | None = Field(default=None, gt=0)
    seuil_article_lent_jours: int | None = Field(default=None, ge=1, le=365)
    objectif_ventes_jour: int | None = Field(default=None, ge=0, le=100)
    arrondi_seuil: Decimal | None = Field(default=None, ge=0)
    arrondi_pas: Decimal | None = Field(default=None, gt=0)


@router.get("/parametres", response_model=ParametresOut)
def lire_parametres(db: Db) -> object:
    return get_parametres(db)


@router.patch("/parametres", response_model=ParametresOut)
def modifier_parametres(data: ParametresUpdate, db: Db) -> object:
    params = get_parametres(db)
    for cle, valeur in data.model_dump(exclude_unset=True).items():
        setattr(params, cle, valeur)
    db.commit()
    return params


@router.get("/search")
def recherche(db: Db, q: str) -> dict[str, list[dict[str, object]]]:
    motif = f"%{q.strip()}%"
    if len(q.strip()) < 2:
        return {"articles": [], "batches": []}
    articles = db.scalars(
        select(Article)
        .where(or_(Article.nom.ilike(motif), Article.marque.ilike(motif), Article.couleur.ilike(motif)))
        .order_by(Article.updated_at.desc())
        .limit(8)
    ).all()
    batches = db.scalars(select(Batch).where(Batch.nom.ilike(motif)).limit(4)).all()
    return {
        "articles": [{"id": a.id, "nom": a.nom, "taille": a.taille, "statut": a.statut} for a in articles],
        "batches": [{"id": b.id, "nom": b.nom} for b in batches],
    }


class Comparaison(BaseModel):
    ca: Decimal
    marge: Decimal
    nb_ventes: int
    ca_precedente: Decimal
    marge_precedente: Decimal
    nb_ventes_precedente: int


@router.get("/dashboard/jour")
def ecran_du_jour(db: Db) -> dict[str, object]:
    params = get_parametres(db)
    articles = stats.tous_les_articles(db)
    maintenant = utcnow()
    aujourdhui = stats.jour_local(maintenant)
    seuil = maintenant - timedelta(days=params.seuil_article_lent_jours)
    lents = [
        a
        for a in articles
        if a.statut == StatutArticle.EN_LIGNE and a.date_publication and a.date_publication <= seuil
    ]
    debut_semaine = aujourdhui - timedelta(days=aujourdhui.weekday())

    def semaine(du: date, au: date) -> stats.Kpis:
        return stats.kpis(articles, params, du, au)

    cette = semaine(debut_semaine, aujourdhui)
    # Semaine précédente arrêtée au même jour de la semaine, pour une comparaison juste.
    precedente = semaine(debut_semaine - timedelta(days=7), aujourdhui - timedelta(days=7))
    ventes_jour = stats.kpis(articles, params, aujourdhui, aujourdhui).nb_ventes
    return {
        "a_publier": sum(1 for a in articles if a.statut == StatutArticle.RECU_A_PUBLIER),
        "commandes_en_attente": sum(1 for a in articles if a.statut == StatutArticle.COMMANDE),
        "litiges": sum(1 for a in articles if a.statut == StatutArticle.LITIGE),
        "articles_lents": [
            {
                "id": a.id,
                "nom": a.nom,
                "taille": a.taille,
                "prix_vente": stats.prix_vente(a),
                "jours_en_ligne": (maintenant - a.date_publication).days if a.date_publication else None,
            }
            for a in sorted(lents, key=lambda a: a.date_publication or datetime.min)
        ],
        "semaine": Comparaison(
            ca=cette.ca_encaisse,
            marge=cette.marge_realisee,
            nb_ventes=cette.nb_ventes,
            ca_precedente=precedente.ca_encaisse,
            marge_precedente=precedente.marge_realisee,
            nb_ventes_precedente=precedente.nb_ventes,
        ),
        "objectif_jour": {"objectif": params.objectif_ventes_jour, "ventes": ventes_jour},
    }


@router.get("/alertes")
def alertes(db: Db) -> dict[str, list[dict[str, object]]]:
    litiges = db.scalars(select(Article).where(Article.statut == StatutArticle.LITIGE)).all()
    return {"litiges": [{"id": a.id, "nom": a.nom} for a in litiges]}
