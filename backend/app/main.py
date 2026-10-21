from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app import scheduler
from app.api import (
    annonces,
    articles,
    auth,
    batches,
    compta,
    import_export,
    mails,
    preuves,
    push,
    sourcing,
    systeme,
    ventes,
)
from app.api.deps import session_requise
from app.config import get_settings
from app.db import SessionLocal
from app.logging import configurer_logs, log
from app.seed.modeles import installer_modeles
from app.seed.regles import installer_regles

configurer_logs(get_settings().log_level)


@asynccontextmanager
async def cycle_de_vie(_: FastAPI) -> AsyncIterator[None]:
    with SessionLocal() as db:
        installer_regles(db)
        installer_modeles(db)
    scheduler.demarrer()
    yield
    scheduler.arreter()


app = FastAPI(
    title="Vinted Manager", docs_url="/api/docs", openapi_url="/api/openapi.json", lifespan=cycle_de_vie
)


@app.exception_handler(RequestValidationError)
async def erreur_validation(_: Request, exc: RequestValidationError) -> JSONResponse:
    champs = [".".join(str(p) for p in e["loc"] if p != "body") for e in exc.errors()]
    return JSONResponse(
        status_code=422,
        content={"detail": f"Données invalides : {', '.join(c for c in champs if c) or 'requête'}."},
    )


@app.exception_handler(Exception)
async def erreur_inattendue(request: Request, exc: Exception) -> JSONResponse:
    log.exception("erreur_inattendue", chemin=request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Erreur inattendue côté serveur. Réessaie."})


@app.get("/health")
@app.get("/api/health")
def health() -> dict[str, str]:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(503, "Base de données inaccessible.") from exc
    return {"status": "ok"}


publique = APIRouter(prefix="/api")
publique.include_router(auth.router)

protegee = APIRouter(prefix="/api", dependencies=[Depends(session_requise)])
for module in (
    annonces,
    articles,
    push,
    batches,
    preuves,
    import_export,
    compta,
    sourcing,
    systeme,
    mails,
    ventes,
):
    protegee.include_router(module.router)

app.include_router(publique)
app.include_router(protegee)
