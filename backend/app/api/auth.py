from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from app.api.deps import Db, session_requise
from app.config import get_settings
from app.logging import log
from app.models import SessionUtilisateur, Utilisateur
from app.services import auth

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: str
    mot_de_passe: str


class MoiOut(BaseModel):
    email: str


def _poser_cookie(response: Response, token: str) -> None:
    s = get_settings()
    response.set_cookie(
        auth.COOKIE_SESSION,
        token,
        max_age=s.session_days * 86400,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )


@router.post("/login", response_model=MoiOut)
def login(data: LoginIn, request: Request, response: Response, db: Db) -> MoiOut:
    ip = request.client.host if request.client else None
    try:
        user = auth.authentifier(db, data.email, data.mot_de_passe, ip)
    except auth.EchecConnexion as exc:
        log.info("login_echec", raison=str(exc))
        raise HTTPException(401, str(exc)) from exc
    token = auth.creer_session(db, user, request.headers.get("user-agent"))
    _poser_cookie(response, token)
    log.info("login_ok")
    return MoiOut(email=user.email)


@router.post("/logout", status_code=204)
def logout(
    response: Response,
    db: Db,
    vm_session: Annotated[str | None, Cookie(alias=auth.COOKIE_SESSION)] = None,
) -> None:
    if vm_session:
        auth.supprimer_session(db, vm_session)
    response.delete_cookie(auth.COOKIE_SESSION, path="/")


@router.get("/me", response_model=MoiOut)
def me(
    db: Db,
    response: Response,
    session: Annotated[SessionUtilisateur, Depends(session_requise)],
    vm_session: Annotated[str | None, Cookie(alias=auth.COOKIE_SESSION)] = None,
) -> MoiOut:
    user = db.get(Utilisateur, session.utilisateur_id)
    if user is None:
        raise HTTPException(401, "Session expirée, reconnecte-toi.")
    if vm_session:
        # Renouvelle aussi le cookie côté navigateur (durée glissante de 30 jours).
        _poser_cookie(response, vm_session)
    return MoiOut(email=user.email)
