"""Photos d'articles : dépôt, génération par l'IA (tâche de fond), choix de version, zip."""

import io
import zipfile
from datetime import datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from app.api.deps import Db, get_parametres
from app.config import get_settings
from app.db import utcnow
from app.models import Article, PhotoArticle
from app.services import images, photos, replicate_client, storage

router = APIRouter(tags=["photos"])
TYPES_ACCEPTES = {"image/jpeg", "image/png", "image/webp"}
TypePhoto = Literal["devant", "dos", "etiquette", "logo", "detail", "defaut"]


class PhotoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    article_id: int
    type: str
    ordre: int
    statut: str
    version_choisie: str
    a_version_generee: bool = False
    modele: str | None
    disposition: str | None
    nb_generations: int
    cout_estime: Decimal
    erreur: str | None
    updated_at: datetime


def _out(p: PhotoArticle) -> PhotoOut:
    o = PhotoOut.model_validate(p)
    o.a_version_generee = bool(p.fichier_genere)
    return o


def _article(db: Db, article_id: int) -> Article:
    a = db.get(Article, article_id)
    if a is None:
        raise HTTPException(404, "Article introuvable.")
    return a


def _photo(db: Db, photo_id: int) -> PhotoArticle:
    p = db.get(PhotoArticle, photo_id)
    if p is None:
        raise HTTPException(404, "Photo introuvable.")
    return p


def _photos_article(db: Db, article_id: int) -> list[PhotoArticle]:
    rang = {t: i for i, t in enumerate(photos.ORDRE_TYPES)}
    return sorted(
        db.scalars(select(PhotoArticle).where(PhotoArticle.article_id == article_id)),
        key=lambda p: (rang.get(p.type, 99), p.ordre, p.id),
    )


async def _lire_image(fichier: UploadFile) -> bytes:
    if (fichier.content_type or "").lower() not in TYPES_ACCEPTES:
        raise HTTPException(
            415,
            "Format non accepté : envoie une photo JPG, PNG ou WEBP (sur iPhone, réglage « Le plus compatible »).",
        )
    max_octets = get_settings().max_upload_mb * 1024 * 1024
    contenu = await fichier.read(max_octets + 1)
    if len(contenu) > max_octets:
        raise HTTPException(413, f"Photo trop lourde (maximum {get_settings().max_upload_mb} Mo).")
    try:
        return images.preparer(contenu)
    except images.ImageInvalide as exc:
        raise HTTPException(415, str(exc)) from exc


@router.get("/articles/{article_id}/photos")
def lister(article_id: int, db: Db) -> dict[str, object]:
    _article(db, article_id)
    liste = _photos_article(db, article_id)
    types = {p.type for p in liste}
    return {
        "photos": [_out(p) for p in liste],
        "manquantes": [t for t in photos.TYPES_OBLIGATOIRES if t not in types],
        "en_cours": any(p.statut == "en_cours" for p in liste),
        "cout_total": sum((p.cout_estime for p in liste), Decimal("0")),
    }


@router.post("/articles/{article_id}/photos", response_model=PhotoOut, status_code=201)
async def deposer(
    article_id: int, db: Db, fichier: UploadFile = File(...), type: TypePhoto = Form(...)
) -> PhotoOut:
    _article(db, article_id)
    contenu = await _lire_image(fichier)
    rang = db.scalar(select(func.count(PhotoArticle.id)).where(PhotoArticle.article_id == article_id)) or 0
    photo = PhotoArticle(
        article_id=article_id,
        type=type,
        ordre=rang,
        fichier_original=storage.ecrire_fichier(f"photos/article-{article_id}", f"{type}.jpg", contenu),
        statut="original" if type == "defaut" else "a_generer",
        version_choisie="original" if type == "defaut" else "genere",
    )
    db.add(photo)
    db.commit()
    db.refresh(photo)
    return _out(photo)


class ModifPhoto(BaseModel):
    type: TypePhoto | None = None
    version_choisie: Literal["genere", "original"] | None = None


@router.patch("/photos/{photo_id}", response_model=PhotoOut)
def modifier(photo_id: int, data: ModifPhoto, db: Db) -> PhotoOut:
    p = _photo(db, photo_id)
    if data.type:
        p.type = data.type
        if data.type == "defaut":
            p.version_choisie, p.statut = "original", "original"
    if data.version_choisie:
        if data.version_choisie == "genere" and not p.fichier_genere:
            raise HTTPException(409, "Cette photo n'a pas encore de version retouchée.")
        if data.version_choisie == "genere" and p.type == "defaut":
            raise HTTPException(409, "Une photo de défaut reste toujours l'originale.")
        p.version_choisie = data.version_choisie
    db.commit()
    return _out(p)


@router.delete("/photos/{photo_id}", status_code=204)
def supprimer(photo_id: int, db: Db) -> None:
    p = _photo(db, photo_id)
    for chemin in (p.fichier_original, p.fichier_genere):
        if chemin:
            storage.supprimer(chemin)
    db.delete(p)
    db.commit()


def _verifier_config(db: Db) -> None:
    if not get_settings().replicate_api_token:
        raise HTTPException(
            409, "La génération de photos n'est pas configurée : REPLICATE_API_TOKEN manquant sur le serveur."
        )
    if not get_parametres(db).photo_fond:
        raise HTTPException(409, "Ajoute d'abord la photo de ton tapis dans Paramètres → Photos.")


def _lancer(db: Db, taches: BackgroundTasks, liste: list[PhotoArticle]) -> list[PhotoOut]:
    for p in liste:
        p.statut, p.erreur = "en_cours", None
    db.commit()
    taches.add_task(photos.tache_generation, [p.id for p in liste])
    return [_out(p) for p in liste]


@router.post("/articles/{article_id}/photos/generer", response_model=list[PhotoOut])
def generer(article_id: int, db: Db, taches: BackgroundTasks, tout: bool = False) -> list[PhotoOut]:
    """Génère les photos pas encore retouchées (ou toutes avec ?tout=true). Les défauts sont ignorés."""
    _article(db, article_id)
    _verifier_config(db)
    liste = [
        p for p in _photos_article(db, article_id)
        if p.type != "defaut" and p.statut != "en_cours" and (tout or p.statut in ("a_generer", "erreur"))
    ]  # fmt: skip
    if not liste:
        raise HTTPException(
            409, "Aucune photo à générer : dépose d'abord les photos (devant, dos, étiquette, logo)."
        )
    return _lancer(db, taches, liste)


@router.post("/photos/{photo_id}/regenerer", response_model=PhotoOut)
def regenerer(photo_id: int, db: Db, taches: BackgroundTasks) -> PhotoOut:
    p = _photo(db, photo_id)
    if p.type == "defaut":
        raise HTTPException(409, "Une photo de défaut n'est jamais retouchée.")
    if p.statut == "en_cours":
        raise HTTPException(409, "Génération déjà en cours pour cette photo.")
    _verifier_config(db)
    return _lancer(db, taches, [p])[0]


@router.get("/photos/{photo_id}/fichier")
def fichier(
    photo_id: int, db: Db, version: Literal["original", "genere", "choisie"] = "choisie"
) -> FileResponse:
    p = _photo(db, photo_id)
    choix = p.version_choisie if version == "choisie" else version
    chemin = p.fichier_genere if choix == "genere" and p.fichier_genere else p.fichier_original
    absolu = storage.chemin_absolu(chemin)
    if not absolu.exists():
        raise HTTPException(404, "Fichier introuvable sur le serveur.")
    return FileResponse(absolu, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=60"})


@router.get("/articles/{article_id}/photos.zip")
def zip_photos(article_id: int, db: Db) -> StreamingResponse:
    """Les versions choisies, numérotées dans l'ordre d'affichage Vinted (devant en premier)."""
    article = _article(db, article_id)
    liste = _photos_article(db, article_id)
    if not liste:
        raise HTTPException(404, "Aucune photo pour cet article.")
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_STORED) as z:
        for i, p in enumerate(liste, start=1):
            chemin = (
                p.fichier_genere if p.version_choisie == "genere" and p.fichier_genere else p.fichier_original
            )
            absolu = storage.chemin_absolu(chemin)
            if absolu.exists():
                z.write(absolu, f"{i:02d}-{p.type}.jpg")
    tampon.seek(0)
    nom = f"photos-{storage.nom_sur(article.nom)[:40]}-{utcnow():%Y%m%d}.zip"
    return StreamingResponse(
        tampon, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{nom}"'}
    )


# --- Paramètres photos ------------------------------------------------------------------------


class ParametresPhotos(BaseModel):
    modele: str
    fond_defini: bool
    configure: bool
    modeles: dict[str, float]
    depense_mois: Decimal
    photos_generees_mois: int


@router.get("/parametres/photos", response_model=ParametresPhotos)
def lire_parametres(db: Db) -> ParametresPhotos:
    p = get_parametres(db)
    debut_mois = utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    lignes = db.scalars(
        select(PhotoArticle).where(PhotoArticle.updated_at >= debut_mois, PhotoArticle.nb_generations > 0)
    ).all()
    return ParametresPhotos(
        modele=p.modele_photos,
        fond_defini=bool(p.photo_fond),
        configure=bool(get_settings().replicate_api_token),
        modeles=replicate_client.PRIX_PAR_IMAGE,
        depense_mois=sum((x.cout_estime for x in lignes), Decimal("0")),
        photos_generees_mois=sum(x.nb_generations for x in lignes),
    )


class ModifParametresPhotos(BaseModel):
    modele: str


@router.put("/parametres/photos", response_model=ParametresPhotos)
def modifier_parametres(data: ModifParametresPhotos, db: Db) -> ParametresPhotos:
    if data.modele not in replicate_client.PRIX_PAR_IMAGE:
        raise HTTPException(422, "Modèle non pris en charge.")
    get_parametres(db).modele_photos = data.modele
    db.commit()
    return lire_parametres(db)


@router.post("/parametres/photos/fond", response_model=ParametresPhotos)
async def deposer_fond(db: Db, fichier: UploadFile = File(...)) -> ParametresPhotos:
    contenu = await _lire_image(fichier)
    p = get_parametres(db)
    ancien = p.photo_fond
    p.photo_fond = storage.ecrire_fichier("photos/fond", "tapis.jpg", contenu)
    db.commit()
    if ancien:
        storage.supprimer(ancien)
    return lire_parametres(db)


@router.get("/parametres/photos/fond")
def fond(db: Db) -> FileResponse:
    p = get_parametres(db)
    if not p.photo_fond or not storage.chemin_absolu(p.photo_fond).exists():
        raise HTTPException(404, "Aucune photo de fond.")
    return FileResponse(storage.chemin_absolu(p.photo_fond), media_type="image/jpeg")
