from datetime import datetime

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel

from app.api.deps import Db, get_parametres
from app.config import get_settings
from app.logging import log
from app.services import excel_export, excel_import
from app.services.stats import tz

router = APIRouter(tags=["import-export"])

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class CommitIn(BaseModel):
    lignes: list[excel_import.LigneImport]
    pistes: list[excel_import.PisteImport]


class EtatImport(BaseModel):
    deja_importe: bool


@router.get("/import/etat", response_model=EtatImport)
def etat(db: Db) -> EtatImport:
    return EtatImport(deja_importe=excel_import.base_deja_importee(db))


@router.post("/import/excel/preview", response_model=excel_import.ApercuImport)
async def apercu(fichier: UploadFile = File(...)) -> excel_import.ApercuImport:
    """Lit le fichier et renvoie l'aperçu. Rien n'est écrit en base."""
    if not (fichier.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(415, "Le fichier doit être un classeur Excel (.xlsx).")
    max_octets = get_settings().max_upload_mb * 1024 * 1024
    contenu = await fichier.read(max_octets + 1)
    if len(contenu) > max_octets:
        raise HTTPException(413, "Fichier trop volumineux.")
    try:
        return excel_import.lire_classeur(contenu)
    except excel_import.ErreurImport as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post("/import/excel/commit")
def valider(data: CommitIn, db: Db) -> dict[str, int]:
    try:
        resultat = excel_import.ecrire_import(db, data.lignes, data.pistes)
    except excel_import.ErreurImport as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    log.info("import_excel", **resultat)
    return resultat


@router.get("/export/excel")
def exporter(db: Db) -> Response:
    contenu = excel_export.generer_export(db, get_parametres(db))
    nom = f"suivi-revente-{datetime.now(tz()):%Y-%m-%d}.xlsx"
    return Response(
        contenu, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="{nom}"'}
    )
