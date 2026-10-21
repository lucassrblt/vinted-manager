from collections import defaultdict
from decimal import Decimal

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.api.deps import Db, get_parametres
from app.models import Article, Batch, PreuveAchat
from app.schemas.stock import ArticleOut, BatchCreate, BatchStats, BatchUpdate, PreuveOut, vers_out
from app.services import calculs, stats, storage
from app.services.remise import repartir_remise
from app.services.statuts import changer_statut

router = APIRouter(prefix="/batches", tags=["batches"])


def _get(db: Db, batch_id: int) -> Batch:
    batch = db.get(Batch, batch_id)
    if batch is None:
        raise HTTPException(404, "Batch introuvable.")
    return batch


@router.get("", response_model=list[BatchStats])
def lister(db: Db) -> list[dict[str, object]]:
    par_batch: dict[int, list[Article]] = defaultdict(list)
    for a in db.scalars(select(Article).where(Article.batch_id.is_not(None))):
        assert a.batch_id is not None
        par_batch[a.batch_id].append(a)
    batches = db.scalars(select(Batch).order_by(Batch.date_commande.desc().nulls_last(), Batch.nom)).all()
    return [stats.stats_batch(b, par_batch.get(b.id, [])) for b in batches]


@router.post("", response_model=BatchStats, status_code=201)
def creer(data: BatchCreate, db: Db) -> dict[str, object]:
    """Crée le batch et ses articles ; la remise globale est répartie au prorata du prix brut."""
    lignes = [ligne for ligne in data.articles for _ in range(ligne.quantite)]
    bruts = [ligne.prix_achat_brut for ligne in lignes]
    try:
        remises = repartir_remise(bruts, data.remise_globale)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    batch = Batch(
        nom=data.nom.strip(),
        fournisseur=data.fournisseur,
        date_commande=data.date_commande,
        total_paye=data.total_paye
        if data.total_paye is not None
        else sum(bruts, Decimal("0")) - data.remise_globale,
        remise_globale=data.remise_globale,
        notes=data.notes,
    )
    db.add(batch)
    articles = []
    for ligne, remise in zip(lignes, remises, strict=True):
        article = Article(
            nom=ligne.nom.strip(),
            marque=ligne.marque,
            categorie=ligne.categorie,
            taille=ligne.taille,
            couleur=ligne.couleur,
            prix_achat_brut=ligne.prix_achat_brut,
            remise=remise,
            prix_achat_net=calculs.prix_achat_net(ligne.prix_achat_brut, remise),
            prix_vente_cible=ligne.prix_vente_cible,
            batch=batch,
            source=data.fournisseur,
            date_achat=data.date_commande,
        )
        db.add(article)
        changer_statut(db, article, data.statut_articles, commentaire="Création du batch")
        articles.append(article)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Un batch porte déjà ce nom.") from exc
    return stats.stats_batch(batch, articles)


@router.get("/{batch_id}")
def detail(batch_id: int, db: Db) -> dict[str, object]:
    batch = _get(db, batch_id)
    articles = list(db.scalars(select(Article).where(Article.batch_id == batch_id).order_by(Article.nom)))
    preuves = db.scalars(select(PreuveAchat).where(PreuveAchat.batch_id == batch_id)).all()
    params = get_parametres(db)
    return {
        "batch": BatchStats.model_validate(stats.stats_batch(batch, articles)),
        "articles": [ArticleOut.model_validate(vers_out(a, params)) for a in articles],
        "preuves": [PreuveOut.model_validate(p) for p in preuves],
    }


@router.patch("/{batch_id}", response_model=BatchStats)
def modifier(batch_id: int, data: BatchUpdate, db: Db) -> dict[str, object]:
    batch = _get(db, batch_id)
    for cle, valeur in data.model_dump(exclude_unset=True).items():
        setattr(batch, cle, valeur)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Un batch porte déjà ce nom.") from exc
    articles = list(db.scalars(select(Article).where(Article.batch_id == batch_id)))
    return stats.stats_batch(batch, articles)


@router.delete("/{batch_id}", status_code=204)
def supprimer(batch_id: int, db: Db) -> None:
    """Supprime le batch ; ses articles sont conservés, sans batch."""
    batch = _get(db, batch_id)
    for preuve in db.scalars(select(PreuveAchat).where(PreuveAchat.batch_id == batch_id)):
        storage.supprimer(preuve.fichier)
    db.delete(batch)
    db.commit()
