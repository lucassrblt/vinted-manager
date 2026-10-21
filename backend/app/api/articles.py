from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import selectinload

from app.api.deps import Db, get_parametres
from app.db import utcnow
from app.models import Article, Batch, EmailVinted, Envoi, HistoriqueStatut, PreuveAchat, Vente
from app.models.enums import StatutArticle
from app.schemas.stock import (
    ActionGroupee,
    ArticleCreate,
    ArticleOut,
    ArticleUpdate,
    ChangementStatut,
    HistoriqueOut,
    Page,
    PreuveOut,
    vers_out,
)
from app.services import calculs, storage
from app.services.statuts import changer_statut

router = APIRouter(prefix="/articles", tags=["articles"])

TRIS = {
    "nom": Article.nom,
    "taille": Article.taille,
    "prix_achat_net": Article.prix_achat_net,
    "prix_vente": func.coalesce(Article.prix_vente_reel, Article.prix_vente_cible),
    "marge": func.coalesce(Article.prix_vente_reel, Article.prix_vente_cible) - Article.prix_achat_net,
    "coefficient": func.coalesce(Article.prix_vente_reel, Article.prix_vente_cible)
    / func.nullif(Article.prix_achat_net, 0),
    "statut": Article.statut,
    "date_publication": Article.date_publication,
    "created_at": Article.created_at,
    "marque": Article.marque,
}


def _get(db: Db, article_id: int) -> Article:
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(404, "Article introuvable.")
    return article


def _filtrer(
    q: Select[Article],
    statut: list[StatutArticle] | None,
    batch_id: list[int] | None,
    marque: list[str] | None,
    categorie: list[str] | None,
    taille: list[str] | None,
    recherche: str | None,
) -> Select[Article]:
    if statut:
        q = q.where(Article.statut.in_([s.value for s in statut]))
    if batch_id:
        q = q.where(Article.batch_id.in_(batch_id))
    if marque:
        q = q.where(Article.marque.in_(marque))
    if categorie:
        q = q.where(Article.categorie.in_(categorie))
    if taille:
        q = q.where(Article.taille.in_(taille))
    if recherche:
        motif = f"%{recherche.strip()}%"
        q = q.where(
            or_(
                Article.nom.ilike(motif),
                Article.marque.ilike(motif),
                Article.couleur.ilike(motif),
                Article.notes.ilike(motif),
            )
        )
    return q


@router.get("", response_model=Page[ArticleOut])
def lister(
    db: Db,
    statut: list[StatutArticle] | None = Query(None),
    batch_id: list[int] | None = Query(None),
    marque: list[str] | None = Query(None),
    categorie: list[str] | None = Query(None),
    taille: list[str] | None = Query(None),
    q: str | None = None,
    tri: str = "created_at",
    ordre: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1),
    taille_page: int = Query(50, ge=1, le=500),
) -> Page[ArticleOut]:
    base = _filtrer(select(Article), statut, batch_id, marque, categorie, taille, q)
    total = db.scalar(select(func.count()).select_from(base.subquery())) or 0
    colonne = TRIS.get(tri, Article.created_at)
    colonne = colonne.asc().nulls_last() if ordre == "asc" else colonne.desc().nulls_last()
    articles = db.scalars(
        base.options(selectinload(Article.batch))
        .order_by(colonne, Article.id.desc())
        .offset((page - 1) * taille_page)
        .limit(taille_page)
    ).all()
    params = get_parametres(db)
    return Page(
        items=[vers_out(a, params) for a in articles], total=total, page=page, taille_page=taille_page
    )


@router.get("/filtres")
def valeurs_filtres(db: Db) -> dict[str, list[str]]:
    """Valeurs distinctes pour alimenter les filtres du tableau de stock."""

    def distinct(col: object) -> list[str]:
        return [v for v in db.scalars(select(col).distinct().order_by(col)).all() if v]  # type: ignore[call-overload]

    return {
        "marques": distinct(Article.marque),
        "categories": distinct(Article.categorie),
        "tailles": distinct(Article.taille),
        "sources": distinct(Article.source),
    }


@router.post("", response_model=ArticleOut, status_code=201)
def creer(data: ArticleCreate, db: Db) -> ArticleOut:
    valeurs = data.model_dump(exclude={"statut", "prix_achat_net"})
    article = Article(**valeurs)
    article.prix_achat_net = (
        data.prix_achat_net
        if data.prix_achat_net is not None
        else calculs.prix_achat_net(data.prix_achat_brut, data.remise)
    )
    if article.prix_achat_brut is None and article.prix_achat_net is not None:
        article.prix_achat_brut = article.prix_achat_net + data.remise
    if data.batch_id is not None and db.get(Batch, data.batch_id) is None:
        raise HTTPException(422, "Batch introuvable.")
    db.add(article)
    changer_statut(db, article, data.statut, commentaire="Création")
    db.commit()
    db.refresh(article)
    return vers_out(article, get_parametres(db))


@router.get("/{article_id}", response_model=ArticleOut)
def detail(article_id: int, db: Db) -> ArticleOut:
    return vers_out(_get(db, article_id), get_parametres(db))


@router.patch("/{article_id}", response_model=ArticleOut)
def modifier(article_id: int, data: ArticleUpdate, db: Db) -> ArticleOut:
    article = _get(db, article_id)
    champs = data.model_dump(exclude_unset=True)
    if "batch_id" in champs and champs["batch_id"] is not None and db.get(Batch, champs["batch_id"]) is None:
        raise HTTPException(422, "Batch introuvable.")
    for cle, valeur in champs.items():
        setattr(article, cle, valeur)
    # Brut ou remise modifiés sans net explicite : on recalcule le net.
    if ("prix_achat_brut" in champs or "remise" in champs) and "prix_achat_net" not in champs:
        article.prix_achat_net = calculs.prix_achat_net(article.prix_achat_brut, article.remise)
    db.commit()
    db.refresh(article)
    return vers_out(article, get_parametres(db))


@router.delete("/{article_id}", status_code=204)
def supprimer(article_id: int, db: Db) -> None:
    article = _get(db, article_id)
    for preuve in db.scalars(select(PreuveAchat).where(PreuveAchat.article_id == article_id)):
        storage.supprimer(preuve.fichier)
    db.delete(article)
    db.commit()


@router.post("/{article_id}/statut", response_model=ArticleOut)
def statut(article_id: int, data: ChangementStatut, db: Db) -> ArticleOut:
    article = _get(db, article_id)
    changer_statut(db, article, data.statut, quand=data.date, commentaire=data.commentaire)
    db.commit()
    db.refresh(article)
    return vers_out(article, get_parametres(db))


@router.get("/{article_id}/timeline", response_model=list[HistoriqueOut])
def timeline(article_id: int, db: Db) -> list[HistoriqueStatut]:
    _get(db, article_id)
    return list(
        db.scalars(
            select(HistoriqueStatut)
            .where(HistoriqueStatut.article_id == article_id)
            .order_by(HistoriqueStatut.date, HistoriqueStatut.id)
        )
    )


@router.get("/{article_id}/liens")
def liens(article_id: int, db: Db) -> dict[str, list[dict[str, object]]]:
    """Ventes, envois, mails et preuves liés à un article (fiche article)."""
    _get(db, article_id)
    ventes = db.scalars(select(Vente).where(Vente.article_id == article_id).order_by(Vente.date_heure)).all()
    envois = (
        db.scalars(select(Envoi).where(Envoi.vente_id.in_([v.id for v in ventes]))).all() if ventes else []
    )
    mails = db.scalars(
        select(EmailVinted).where(EmailVinted.article_id == article_id).order_by(EmailVinted.date.desc())
    ).all()
    preuves = db.scalars(
        select(PreuveAchat).where(PreuveAchat.article_id == article_id).order_by(PreuveAchat.date_upload)
    ).all()
    return {
        "ventes": [
            {
                "id": v.id,
                "prix": v.prix,
                "date_heure": v.date_heure,
                "acheteur": v.acheteur,
                "numero_commande": v.numero_commande,
                "auto_rapproche": v.auto_rapproche,
            }
            for v in ventes
        ],
        "envois": [
            {
                "id": e.id,
                "statut": e.statut,
                "transporteur": e.transporteur,
                "date_limite_envoi": e.date_limite_envoi,
                "date_depot": e.date_depot,
            }
            for e in envois
        ],
        "mails": [
            {"id": m.id, "date": m.date, "sujet": m.sujet, "type_detecte": m.type_detecte} for m in mails
        ],
        "preuves": [PreuveOut.model_validate(p).model_dump() for p in preuves],
    }


@router.post("/bulk")
def actions_groupees(data: ActionGroupee, db: Db) -> dict[str, int]:
    articles = db.scalars(select(Article).where(Article.id.in_(data.ids))).all()
    if len(articles) != len(set(data.ids)):
        raise HTTPException(404, "Un ou plusieurs articles sont introuvables.")
    if data.action == "statut":
        if data.statut is None:
            raise HTTPException(422, "Statut manquant.")
        for a in articles:
            changer_statut(db, a, data.statut, commentaire="Action groupée")
    elif data.action == "publie_aujourdhui":
        maintenant = utcnow()
        for a in articles:
            if a.statut == StatutArticle.EN_LIGNE:
                a.date_publication = maintenant
            else:
                changer_statut(
                    db, a, StatutArticle.EN_LIGNE, quand=maintenant, commentaire="Publié", forcer_date=True
                )
    elif data.action == "batch":
        if data.batch_id is not None and db.get(Batch, data.batch_id) is None:
            raise HTTPException(422, "Batch introuvable.")
        for a in articles:
            a.batch_id = data.batch_id
    elif data.action == "supprimer":
        for a in articles:
            for preuve in db.scalars(select(PreuveAchat).where(PreuveAchat.article_id == a.id)):
                storage.supprimer(preuve.fichier)
            db.delete(a)
    else:
        raise HTTPException(422, "Action inconnue.")
    db.commit()
    return {"modifies": len(articles)}
