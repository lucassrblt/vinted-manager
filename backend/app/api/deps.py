from typing import Annotated

from fastapi import Cookie, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Parametres, SessionUtilisateur
from app.services.auth import COOKIE_SESSION, session_valide

Db = Annotated[Session, Depends(get_db)]


def session_requise(
    db: Db, vm_session: Annotated[str | None, Cookie(alias=COOKIE_SESSION)] = None
) -> SessionUtilisateur:
    if not vm_session:
        raise HTTPException(401, "Session expirée, reconnecte-toi.")
    session = session_valide(db, vm_session)
    if session is None:
        raise HTTPException(401, "Session expirée, reconnecte-toi.")
    return session


def get_parametres(db: Session) -> Parametres:
    params = db.get(Parametres, 1)
    if params is None:
        params = Parametres(id=1)
        db.add(params)
        db.commit()
    return params
