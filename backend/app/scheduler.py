"""Tâches planifiées, dans le process de l'API (une seule instance en production)."""

from apscheduler.schedulers.background import BackgroundScheduler

from app.config import get_settings
from app.db import SessionLocal
from app.logging import log
from app.models import Parametres
from app.services import imap_sync
from app.services.auth import nettoyer_sessions

planificateur: BackgroundScheduler | None = None


def tache_synchro() -> None:
    with SessionLocal() as db:
        params = db.get(Parametres, 1)
        if params is None or not imap_sync.imap_configuree(params):
            return  # boîte mail non configurée : rien à faire
        try:
            imap_sync.synchroniser(db, params)
        except imap_sync.ErreurImap as exc:
            log.info("sync_ignoree", raison=str(exc))
        except Exception:
            log.exception("sync_erreur")


def tache_nettoyage() -> None:
    with SessionLocal() as db:
        nettoyer_sessions(db)


def demarrer() -> None:
    global planificateur
    s = get_settings()
    if not s.scheduler_actif or planificateur is not None:
        return
    planificateur = BackgroundScheduler(timezone=s.timezone)
    planificateur.add_job(
        tache_synchro,
        "interval",
        minutes=s.intervalle_synchro_minutes,
        id="synchro",
        max_instances=1,
        coalesce=True,
    )
    planificateur.add_job(tache_nettoyage, "cron", hour=4, id="nettoyage")
    planificateur.start()
    log.info("planificateur_demarre")


def arreter() -> None:
    global planificateur
    if planificateur is not None:
        planificateur.shutdown(wait=False)
        planificateur = None
