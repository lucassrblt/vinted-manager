"""Abonnements push, préférences de notifications et sauvegarde complète."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from starlette.background import BackgroundTask

from app.api.deps import Db, get_parametres
from app.config import get_settings
from app.models import AbonnementPush
from app.services import backup, push

router = APIRouter(tags=["notifications"])


@router.get("/push/config")
def config_push() -> dict[str, Any]:
    return {"cle_publique": get_settings().vapid_public_key or None, "configure": push.configure()}


class CleAbonnement(BaseModel):
    p256dh: str = Field(min_length=10, max_length=255)
    auth: str = Field(min_length=8, max_length=255)


class AbonnementIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=1000)
    keys: CleAbonnement


class AbonnementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    endpoint: str
    user_agent: str | None
    created_at: datetime


@router.get("/push/abonnements", response_model=list[AbonnementOut])
def lister(db: Db) -> list[AbonnementPush]:
    return list(db.scalars(select(AbonnementPush).order_by(AbonnementPush.created_at.desc())))


@router.post("/push/abonnements", response_model=AbonnementOut, status_code=201)
def abonner(data: AbonnementIn, request: Request, db: Db) -> AbonnementPush:
    if not data.endpoint.startswith("https://"):
        raise HTTPException(422, "Adresse d'abonnement invalide.")
    existant = db.scalar(select(AbonnementPush).where(AbonnementPush.endpoint == data.endpoint))
    abonnement = existant or AbonnementPush(endpoint=data.endpoint)
    abonnement.p256dh = data.keys.p256dh
    abonnement.auth = data.keys.auth
    abonnement.user_agent = (request.headers.get("user-agent") or "")[:255]
    db.add(abonnement)
    db.commit()
    db.refresh(abonnement)
    return abonnement


@router.delete("/push/abonnements/{abonnement_id}", status_code=204)
def desabonner(abonnement_id: int, db: Db) -> None:
    abonnement = db.get(AbonnementPush, abonnement_id)
    if abonnement is None:
        raise HTTPException(404, "Appareil introuvable.")
    db.delete(abonnement)
    db.commit()


@router.post("/push/test")
def tester(db: Db) -> dict[str, int]:
    if not push.configure():
        raise HTTPException(
            409, "Les notifications ne sont pas configurées sur le serveur (clés VAPID absentes)."
        )
    nb = push.envoyer(
        db,
        "test",
        "Notification de test",
        "Les notifications fonctionnent sur cet appareil.",
        "/",
        forcer=True,
    )
    if nb == 0:
        raise HTTPException(409, "Aucun appareil abonné : active d'abord les notifications sur cet appareil.")
    return {"appareils": nb}


class PreferencesNotifications(BaseModel):
    vente: bool = True
    litige: bool = True
    offre: bool = True
    rappel_envois: bool = True


@router.get("/parametres/notifications", response_model=PreferencesNotifications)
def lire_preferences(db: Db) -> PreferencesNotifications:
    return PreferencesNotifications(**(get_parametres(db).notifications or {}))


@router.put("/parametres/notifications", response_model=PreferencesNotifications)
def enregistrer_preferences(data: PreferencesNotifications, db: Db) -> PreferencesNotifications:
    params = get_parametres(db)
    params.notifications = data.model_dump()
    db.commit()
    return data


@router.get("/backup/complet.zip")
def sauvegarde(db: Db) -> FileResponse:
    chemin = backup.generer(db, get_parametres(db))
    return FileResponse(
        chemin,
        media_type="application/zip",
        filename=chemin.name,
        background=BackgroundTask(chemin.unlink, missing_ok=True),
    )
