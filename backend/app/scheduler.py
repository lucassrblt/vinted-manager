"""Tâches planifiées, dans le process de l'API (une seule instance en production)."""

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select

from app.config import get_settings
from app.db import SessionLocal, utcnow
from app.logging import log
from app.models import Envoi, Parametres
from app.models.enums import StatutEnvoi
from app.services import imap_sync, push
from app.services.auth import nettoyer_sessions
from app.services.stats import jour_local

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


def tache_rappel_envois() -> None:
    """9 h (heure de Paris) : rappel des colis à déposer aujourd'hui ou en retard."""
    with SessionLocal() as db:
        aujourdhui = jour_local(utcnow())
        limites = db.scalars(
            select(Envoi.date_limite_envoi).where(
                Envoi.statut.in_([StatutEnvoi.A_IMPRIMER, StatutEnvoi.IMPRIME])
            )
        ).all()
        jours = [jour_local(d) for d in limites if d is not None]
        retard = sum(1 for j in jours if j < aujourdhui)
        du_jour = sum(1 for j in jours if j == aujourdhui)
        if retard + du_jour == 0:
            return
        morceaux = []
        if du_jour:
            morceaux.append(f"{du_jour} à déposer aujourd'hui")
        if retard:
            morceaux.append(f"{retard} en retard")
        push.envoyer(
            db, "rappel_envois", f"{retard + du_jour} colis à envoyer", " · ".join(morceaux), "/envois"
        )


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
    planificateur.add_job(tache_rappel_envois, "cron", hour=9, minute=0, id="rappel_envois")
    planificateur.add_job(tache_nettoyage, "cron", hour=4, id="nettoyage")
    planificateur.start()
    log.info("planificateur_demarre")


def arreter() -> None:
    global planificateur
    if planificateur is not None:
        planificateur.shutdown(wait=False)
        planificateur = None
