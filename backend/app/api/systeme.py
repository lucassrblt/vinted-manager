"""Paramètres, recherche globale, écran du jour (version étape 1) et alertes."""

from datetime import date, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select

from app.api.deps import Db, get_parametres
from app.db import utcnow
from app.models import Article, Batch, EmailVinted, Envoi, Message
from app.models.enums import StatutArticle, StatutEnvoi, StatutMessage, StatutTraitementEmail, TypeEmail
from app.services import prix_conseille, stats

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
    vendus = [a for a in articles if stats.est_vendu(a)]

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
                "prix_suggere": prix_conseille.nouveau_prix_article_lent(
                    a, prix_conseille.calculer(a, vendus, params), params
                ),
            }
            for a in sorted(lents, key=lambda a: a.date_publication or datetime.min)
        ],
        "messages_a_traiter": db.scalar(
            select(func.count(Message.id)).where(Message.statut == StatutMessage.A_TRAITER)
        )
        or 0,
        "semaine": Comparaison(
            ca=cette.ca_encaisse,
            marge=cette.marge_realisee,
            nb_ventes=cette.nb_ventes,
            ca_precedente=precedente.ca_encaisse,
            marge_precedente=precedente.marge_realisee,
            nb_ventes_precedente=precedente.nb_ventes,
        ),
        "objectif_jour": {"objectif": params.objectif_ventes_jour, "ventes": ventes_jour},
        "envois": _compteurs_envois(db, aujourdhui),
        "ventes_a_confirmer": _compter_mails(db, TypeEmail.VENTE, StatutTraitementEmail.NOUVEAU),
        "mails_non_classes": _compter_mails(db, None, StatutTraitementEmail.A_CLASSER),
    }


def _compteurs_envois(db: Db, aujourdhui: date) -> dict[str, int]:
    limites = db.scalars(
        select(Envoi.date_limite_envoi).where(Envoi.statut.in_([StatutEnvoi.A_IMPRIMER, StatutEnvoi.IMPRIME]))
    ).all()
    jours = [stats.jour_local(d) for d in limites if d is not None]
    return {
        "a_preparer": len(limites),
        "en_retard": sum(1 for j in jours if j < aujourdhui),
        "aujourdhui": sum(1 for j in jours if j == aujourdhui),
    }


def _compter_mails(db: Db, type_email: TypeEmail | None, statut: StatutTraitementEmail) -> int:
    q = select(func.count(EmailVinted.id)).where(EmailVinted.statut_traitement == statut)
    if type_email:
        q = q.where(EmailVinted.type_detecte == type_email)
    return db.scalar(q) or 0


@router.get("/alertes")
def alertes(db: Db) -> dict[str, list[dict[str, object]]]:
    litiges = db.scalars(select(Article).where(Article.statut == StatutArticle.LITIGE)).all()
    return {"litiges": [{"id": a.id, "nom": a.nom} for a in litiges]}
