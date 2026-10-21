import io
import zipfile

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import or_, select

from app.api.deps import Db
from app.models import Article, Batch, PreuveAchat
from app.models.enums import TypePreuve
from app.schemas.stock import PreuveOut
from app.services import storage

router = APIRouter(tags=["preuves"])


@router.post("/preuves", response_model=PreuveOut, status_code=201)
async def ajouter(
    db: Db,
    fichier: UploadFile = File(...),
    type: TypePreuve = Form(TypePreuve.AUTRE),
    article_id: int | None = Form(None),
    batch_id: int | None = Form(None),
    note: str | None = Form(None),
) -> PreuveAchat:
    if (article_id is None) == (batch_id is None):
        raise HTTPException(422, "Indique un article ou un batch (un seul des deux).")
    if article_id is not None and db.get(Article, article_id) is None:
        raise HTTPException(404, "Article introuvable.")
    if batch_id is not None and db.get(Batch, batch_id) is None:
        raise HTTPException(404, "Batch introuvable.")
    dossier = f"preuves/{'article' if article_id else 'batch'}-{article_id or batch_id}"
    relatif, taille, mime = await storage.enregistrer_upload(fichier, dossier, storage.TYPES_PREUVES)
    preuve = PreuveAchat(
        article_id=article_id,
        batch_id=batch_id,
        type=type,
        fichier=relatif,
        nom_original=(fichier.filename or "fichier")[:255],
        mime=mime,
        taille_octets=taille,
        note=note,
    )
    db.add(preuve)
    db.commit()
    db.refresh(preuve)
    return preuve


@router.get("/preuves/{preuve_id}/fichier")
def telecharger(preuve_id: int, db: Db, telechargement: bool = False) -> FileResponse:
    preuve = db.get(PreuveAchat, preuve_id)
    if preuve is None:
        raise HTTPException(404, "Preuve introuvable.")
    chemin = storage.chemin_absolu(preuve.fichier)
    if not chemin.exists():
        raise HTTPException(404, "Le fichier n'existe plus sur le serveur.")
    return FileResponse(
        chemin,
        media_type=preuve.mime,
        filename=preuve.nom_original,
        content_disposition_type="attachment" if telechargement else "inline",
    )


@router.delete("/preuves/{preuve_id}", status_code=204)
def supprimer(preuve_id: int, db: Db) -> None:
    preuve = db.get(PreuveAchat, preuve_id)
    if preuve is None:
        raise HTTPException(404, "Preuve introuvable.")
    storage.supprimer(preuve.fichier)
    db.delete(preuve)
    db.commit()


@router.get("/articles/{article_id}/preuves.zip")
def zip_preuves(article_id: int, db: Db) -> StreamingResponse:
    """Preuves de l'article et de son batch, en un seul zip (utile en cas de litige)."""
    article = db.get(Article, article_id)
    if article is None:
        raise HTTPException(404, "Article introuvable.")
    conditions = [PreuveAchat.article_id == article_id]
    if article.batch_id:
        conditions.append(PreuveAchat.batch_id == article.batch_id)
    preuves = db.scalars(select(PreuveAchat).where(or_(*conditions))).all()
    if not preuves:
        raise HTTPException(404, "Aucune preuve d'achat pour cet article.")
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        for i, p in enumerate(preuves, start=1):
            chemin = storage.chemin_absolu(p.fichier)
            if chemin.exists():
                origine = "batch" if p.batch_id else "article"
                z.write(chemin, f"{i:02d}_{origine}_{p.type}_{storage.nom_sur(p.nom_original)}")
    tampon.seek(0)
    nom = f"preuves_article_{article_id}.zip"
    return StreamingResponse(
        tampon, media_type="application/zip", headers={"Content-Disposition": f'attachment; filename="{nom}"'}
    )
