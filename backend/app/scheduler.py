"""Tâches planifiées, dans le process de l'API (une seule instance en production)."""

from datetime import timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import delete, select

from app.config import get_settings
from app.db import SessionLocal, utcnow
from app.logging import log
from app.models import Envoi, Parametres, SyncLog
from app.models.enums import StatutEnvoi
from app.services import extension, imap_idle, imap_sync, push, republication, telegram
from app.services.auth import nettoyer_sessions
from app.services.stats import jour_local

planificateur: BackgroundScheduler | None = None


def tache_synchro() -> None:
    with SessionLocal() as db:
        params = db.get(Parametres, 1)
        if params is None or not imap_sync.comptes_actifs(db):
            return  # aucune boîte mail configurée : rien à faire
        try:
            imap_sync.synchroniser(db, params)
        except imap_sync.ErreurImap as exc:
            log.info("sync_ignoree", raison=str(exc))
        except Exception:
            log.exception("sync_erreur")


def synchro_sur_nouveau_mail() -> bool:
    """Appelée par l'écoute temps réel. False si une synchro est déjà en cours (à réessayer)."""
    with SessionLocal() as db:
        params = db.get(Parametres, 1)
        if params is None:
            return True
        try:
            imap_sync.synchroniser(db, params)
        except imap_sync.SynchroEnCours:
            return False
        except imap_sync.ErreurImap as exc:
            log.info("sync_ignoree", raison=str(exc))
        except Exception:
            log.exception("sync_erreur")
    return True


def tache_ecoute() -> None:
    try:
        imap_idle.surveiller(synchro_sur_nouveau_mail)
    except Exception:
        log.exception("ecoute_surveillance_erreur")


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


def tache_telegram() -> None:
    """Relève les messages du bot (long polling court : pas de webhook à exposer)."""
    try:
        with SessionLocal() as db:
            telegram.relever(db)
    except Exception:
        log.exception("telegram_erreur")


def tache_surveillance() -> None:
    """Extension silencieuse ou onglet Vinted fermé depuis 5 min : alerte."""
    try:
        with SessionLocal() as db:
            extension.surveiller(db)
    except Exception:
        log.exception("surveillance_erreur")


def tache_republication() -> None:
    """Toutes les 30 min : republications dues (au plus une programmée par compte)."""
    try:
        with SessionLocal() as db:
            republication.planifier(db)
    except Exception:
        log.exception("republication_erreur")


def tache_nettoyage() -> None:
    with SessionLocal() as db:
        nettoyer_sessions(db)
        # Une synchro par minute : on ne garde que la dernière semaine du journal.
        db.execute(delete(SyncLog).where(SyncLog.debut < utcnow() - timedelta(days=7)))
        db.commit()


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
    if s.ecoute_temps_reel:
        planificateur.add_job(
            tache_ecoute, "interval", minutes=1, id="ecoute", next_run_time=utcnow(), max_instances=1
        )
    planificateur.add_job(tache_rappel_envois, "cron", hour=9, minute=0, id="rappel_envois")
    planificateur.add_job(tache_nettoyage, "cron", hour=4, id="nettoyage")
    planificateur.add_job(tache_surveillance, "interval", minutes=1, id="surveillance", coalesce=True)
    planificateur.add_job(tache_republication, "interval", minutes=30, id="republication", coalesce=True)
    if telegram.configure():
        planificateur.add_job(
            tache_telegram, "interval", seconds=5, id="telegram", max_instances=1, coalesce=True
        )
    planificateur.start()
    log.info("planificateur_demarre")


def arreter() -> None:
    global planificateur
    if planificateur is not None:
        planificateur.shutdown(wait=False)
        planificateur = None
    imap_idle.arreter_tout()
