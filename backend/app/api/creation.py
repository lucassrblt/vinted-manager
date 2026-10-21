"""Création d'annonce à partir des photos : analyse par l'IA, retouche en tâche de fond, provenance.

Parcours : déposer les photos -> l'IA classe les photos, lit l'étiquette et rédige l'annonce (une seule
requête) -> la retouche démarre aussitôt -> on choisit la provenance (article du stock, batch ou pièce
perso) -> on copie l'annonce sur Vinted et on marque l'article publié.
"""

from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import Db, get_parametres
from app.api.photos import _lire_image
from app.config import get_settings
from app.logging import log
from app.models import Article, Batch, EmailVinted, PhotoArticle
from app.models.enums import StatutArticle, TypeEmail
from app.services import ia, photos, rapprochement, storage
from app.services.marques import detecter_marque, normaliser
from app.services.statuts import changer_statut

router = APIRouter(tags=["annonces"])

MAX_PHOTOS = 12
NB_EXEMPLES_VENTES = 25
SOURCE_PERSO = "Pièce perso"
# Champs de la fiche recopiés sur l'article du stock choisi
CHAMPS_FICHE = (
    "marque", "modele", "categorie", "taille", "couleur", "etat", "matiere", "defauts",
    "titre_annonce", "description_annonce", "mots_cles_annonce",
)  # fmt: skip


def _dernieres_ventes(db: Db) -> list[str]:
    """Titres réellement publiés sur Vinted et prix de vente (mails de vente) : l'IA s'y cale pour le
    format des titres et le niveau de prix."""
    titres: list[str] = []
    for mail in db.scalars(
        select(EmailVinted)
        .where(EmailVinted.type_detecte == TypeEmail.VENTE)
        .order_by(EmailVinted.date.desc())
    ):
        d = mail.donnees_extraites or {}
        titre = d.get("titre_article")
        if titre and not any(t.startswith(f"{titre} (") or t == titre for t in titres):
            titres.append(f"{titre} (vendu {d['prix']} €)" if d.get("prix") else str(titre))
        if len(titres) >= NB_EXEMPLES_VENTES:
            break
    return titres


def retouche_possible(db: Db) -> bool:
    return bool(get_settings().replicate_api_token and get_parametres(db).photo_fond)


def _types_uniques(types: list[str]) -> list[str]:
    """Une seule photo « devant » et une seule « dos » (les suivantes deviennent des détails)."""
    vus: set[str] = set()
    resultat: list[str] = []
    for t in types:
        t = t if t in photos.TYPES else "detail"
        if t in ("devant", "dos") and t in vus:
            t = "detail"
        vus.add(t)
        resultat.append(t)
    return resultat


@router.post("/annonces/nouvelle", status_code=201)
async def nouvelle_annonce(
    db: Db, taches: BackgroundTasks, photos_deposees: list[UploadFile] = File(..., alias="photos")
) -> dict[str, Any]:
    if not photos_deposees:
        raise HTTPException(422, "Dépose au moins une photo.")
    if len(photos_deposees) > MAX_PHOTOS:
        raise HTTPException(422, f"{MAX_PHOTOS} photos maximum par annonce.")
    contenus = [await _lire_image(f) for f in photos_deposees]

    analyse: ia.AnalysePhotos | None = None
    erreur_ia: str | None = None
    try:
        analyse = ia.analyser_photos(contenus, _dernieres_ventes(db))
    except ia.ErreurIA as exc:
        erreur_ia = str(exc)  # l'article est créé quand même : on complète la fiche à la main
        log.warning("analyse_photos_erreur", erreur=erreur_ia)

    article = Article(nom=(analyse.titre if analyse else "") or "Nouvel article")
    if analyse:
        for champ in ("marque", "modele", "categorie", "taille", "couleur", "matiere", "defauts"):
            setattr(article, champ, getattr(analyse, champ) or None)
        article.etat = analyse.etat if analyse.etat in ia.ETATS else None
        article.titre_annonce = analyse.titre
        article.description_annonce = analyse.description
        article.mots_cles_annonce = ", ".join(analyse.mots_cles)
        if analyse.prix_estime:
            article.prix_vente_cible = Decimal(str(round(analyse.prix_estime)))  # proposition, modifiable
    db.add(article)
    changer_statut(db, article, StatutArticle.RECU_A_PUBLIER, commentaire="Créé depuis les photos")
    db.flush()

    types = _types_uniques(
        analyse.types if analyse else ["devant", "dos", "etiquette", "logo"] + ["detail"] * 12
    )
    for i, (contenu, type_photo) in enumerate(zip(contenus, types, strict=False)):
        db.add(
            PhotoArticle(
                article_id=article.id,
                type=type_photo,
                ordre=i,
                fichier_original=storage.ecrire_fichier(
                    f"photos/article-{article.id}", f"{type_photo}.jpg", contenu
                ),
                statut="original" if type_photo == "defaut" else "a_generer",
                version_choisie="original" if type_photo == "defaut" else "genere",
            )
        )
    db.commit()

    retouche = retouche_possible(db)
    if retouche:
        a_retoucher = list(
            db.scalars(
                select(PhotoArticle).where(
                    PhotoArticle.article_id == article.id, PhotoArticle.type != "defaut"
                )
            )
        )
        for p in a_retoucher:
            p.statut = "en_cours"
        db.commit()
        taches.add_task(photos.tache_generation, [p.id for p in a_retoucher], False)
    return {"article_id": article.id, "erreur_ia": erreur_ia, "retouche_lancee": retouche}


# --- Provenance -------------------------------------------------------------------------------


@router.get("/annonces/{article_id}/correspondances")
def correspondances(article_id: int, db: Db) -> list[dict[str, Any]]:
    """Articles du stock pas encore publiés qui ressemblent à celui-ci (même marque, même taille)."""
    a = _article(db, article_id)
    titre = a.titre_annonce or a.nom
    marque = a.marque or detecter_marque(titre)
    taille = normaliser(a.taille).replace(" ", "") if a.taille else rapprochement.taille_du_titre(titre)
    stock = db.scalars(
        select(Article).where(
            Article.id != a.id,
            Article.perso.is_(False),
            Article.statut.in_([StatutArticle.COMMANDE.value, StatutArticle.RECU_A_PUBLIER.value]),
        )
    ).all()
    resultat: list[dict[str, Any]] = []
    for s in stock:
        marque_stock = s.marque or detecter_marque(s.nom)
        if marque and marque_stock and normaliser(marque) != normaliser(marque_stock):
            continue
        if taille and s.taille and normaliser(s.taille).replace(" ", "") != taille:
            continue
        score = rapprochement.score_titre(titre, s)
        if marque and marque_stock:
            score += 10  # même marque confirmée
        if score >= 45:
            resultat.append(
                {
                    "id": s.id,
                    "nom": s.nom,
                    "taille": s.taille,
                    "statut": s.statut,
                    "batch_nom": s.batch.nom if s.batch else None,
                    "prix_achat_net": s.prix_achat_net,
                    "score": round(min(score, 100)),
                }
            )
    resultat.sort(key=lambda x: x["score"], reverse=True)
    return resultat[:5]


class ProvenanceIn(BaseModel):
    mode: Literal["stock", "batch", "perso"]
    article_stock_id: int | None = None
    batch_id: int | None = None
    prix_achat: Decimal | None = Field(default=None, ge=0)


@router.post("/annonces/{article_id}/provenance")
def provenance(article_id: int, data: ProvenanceIn, db: Db) -> dict[str, Any]:
    a = _article(db, article_id)
    if data.mode == "stock":
        if data.article_stock_id is None or data.article_stock_id == a.id:
            raise HTTPException(422, "Choisis l'article du stock.")
        cible = _article(db, data.article_stock_id)
        _fusionner(db, a, cible)
        db.commit()
        return {"article_id": cible.id}
    if data.mode == "batch":
        if data.batch_id is not None and db.get(Batch, data.batch_id) is None:
            raise HTTPException(422, "Batch introuvable.")
        a.perso = False
        a.batch_id = data.batch_id
        if a.source == SOURCE_PERSO:
            a.source = None
        if data.prix_achat is not None:
            a.prix_achat_brut = a.prix_achat_net = data.prix_achat
    else:
        marquer_perso(a)
    db.commit()
    return {"article_id": a.id}


def marquer_perso(a: Article) -> None:
    a.perso = True
    a.batch_id = None
    a.source = SOURCE_PERSO
    a.prix_achat_brut = a.prix_achat_net = Decimal("0")
    a.remise = Decimal("0")


def _fusionner(db: Db, brouillon: Article, cible: Article) -> None:
    """L'annonce créée depuis les photos complète l'article du stock (photos, fiche, annonce)."""
    for champ in CHAMPS_FICHE:
        valeur = getattr(brouillon, champ)
        if valeur:
            setattr(cible, champ, valeur)
    for p in db.scalars(select(PhotoArticle).where(PhotoArticle.article_id == brouillon.id)):
        p.article_id = cible.id
    if cible.statut == StatutArticle.COMMANDE:
        changer_statut(db, cible, StatutArticle.RECU_A_PUBLIER, commentaire="Photos prises : article reçu")
    db.flush()
    db.delete(brouillon)


def _article(db: Db, article_id: int) -> Article:
    a = db.get(Article, article_id)
    if a is None:
        raise HTTPException(404, "Article introuvable.")
    return a
