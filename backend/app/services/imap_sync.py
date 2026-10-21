"""Synchronisation IMAP des mails Vinted.

Garanties : le dossier est ouvert en lecture seule (EXAMINE) et les messages sont lus avec
BODY.PEEK[] ; aucun mail n'est jamais supprimé, déplacé ni marqué comme lu.
"""

import contextlib
import imaplib
import socket
import ssl
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.logging import log
from app.models import CompteVinted, Parametres, SyncLog
from app.services import crypto
from app.services.email_parser import lire_mail
from app.services.notifications import annuler_en_attente
from app.services.traitement import enregistrer_mail

PREMIERE_SYNCHRO_JOURS = 30
TIMEOUT_SECONDES = 30
MOIS_IMAP = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

PRESETS = {
    "gmail": {"serveur": "imap.gmail.com", "port": 993},
    "outlook": {"serveur": "outlook.office365.com", "port": 993},
    "orange": {"serveur": "imap.orange.fr", "port": 993},
}

_verrou = threading.Lock()


class ErreurImap(Exception):
    pass


@dataclass
class ConfigImap:
    serveur: str
    port: int
    email: str
    mot_de_passe: str
    dossier: str = "INBOX"


FabriqueClient = Callable[[str, int], Any]


def _client_ssl(serveur: str, port: int) -> imaplib.IMAP4_SSL:
    return imaplib.IMAP4_SSL(serveur, port, timeout=TIMEOUT_SECONDES)


def comptes_actifs(db: Session) -> list[CompteVinted]:
    return list(
        db.scalars(select(CompteVinted).where(CompteVinted.actif.is_(True)).order_by(CompteVinted.id))
    )


def noms_comptes(db: Session) -> dict[int, str]:
    return {c.id: c.nom for c in db.scalars(select(CompteVinted))}


def config_depuis(compte: CompteVinted) -> ConfigImap:
    return ConfigImap(
        serveur=compte.imap_serveur,
        port=compte.imap_port or 993,
        email=compte.imap_email,
        mot_de_passe=crypto.dechiffrer(compte.imap_mot_de_passe_chiffre),
        dossier=compte.imap_dossier or "INBOX",
    )


def _message_erreur(exc: Exception, cfg: ConfigImap) -> str:
    texte = str(exc)
    gmail = "gmail" in cfg.serveur.lower()
    if isinstance(exc, socket.gaierror):
        return f"Serveur « {cfg.serveur} » introuvable : vérifie l'adresse du serveur IMAP."
    if isinstance(exc, (TimeoutError, socket.timeout, ConnectionRefusedError)):
        return f"Le serveur {cfg.serveur}:{cfg.port} ne répond pas : vérifie le serveur et le port (993 en général)."
    if isinstance(exc, ssl.SSLError):
        return "Erreur de connexion sécurisée (SSL) : le port doit être 993 avec une connexion SSL."
    if isinstance(exc, imaplib.IMAP4.error):
        if gmail and "Lookup failed" in texte:
            return f"Gmail ne connaît pas l'adresse {cfg.email} : vérifie qu'elle est bien écrite."
        if gmail and (
            "Application-specific password" in texte
            or "AUTHENTICATIONFAILED" in texte
            or "Invalid credentials" in texte
        ):
            return (
                "Gmail refuse la connexion. Gmail n'accepte pas ton mot de passe habituel : active la validation "
                "en deux étapes sur ton compte Google, puis crée un « mot de passe d'application » sur "
                "https://myaccount.google.com/apppasswords et colle ici les 16 caractères."
            )
        if (
            "AUTHENTICATIONFAILED" in texte
            or "LOGIN failed" in texte
            or "authentication failed" in texte.lower()
        ):
            return "Email ou mot de passe refusé par le serveur. Vérifie-les (certains fournisseurs exigent un mot de passe d'application)."
        return f"Le serveur IMAP a refusé la demande : {texte[:200]}"
    return f"Connexion impossible : {texte[:200]}"


def _ouvrir(cfg: ConfigImap, fabrique: FabriqueClient) -> Any:
    try:
        client = fabrique(cfg.serveur, cfg.port)
        client.login(cfg.email, cfg.mot_de_passe)
        statut, _ = client.select(_dossier(cfg.dossier), readonly=True)
    except Exception as exc:
        raise ErreurImap(_message_erreur(exc, cfg)) from exc
    if statut != "OK":
        raise ErreurImap(f"Dossier « {cfg.dossier} » introuvable sur la boîte mail.")
    return client


def _dossier(nom: str) -> str:
    return f'"{nom}"' if " " in nom and not nom.startswith('"') else nom


def tester_connexion(cfg: ConfigImap, fabrique: FabriqueClient = _client_ssl) -> int:
    """Se connecte et compte les mails du dossier. Lève ErreurImap avec un message clair."""
    client = _ouvrir(cfg, fabrique)
    try:
        _, donnees = client.uid("SEARCH", None, "ALL")
        return len(donnees[0].split()) if donnees and donnees[0] else 0
    finally:
        _fermer(client)


def _fermer(client: Any) -> None:
    with contextlib.suppress(Exception):  # la connexion est peut-être déjà coupée
        client.logout()


def date_imap(d: datetime) -> str:
    return f"{d.day:02d}-{MOIS_IMAP[d.month - 1]}-{d.year}"


def critere_expediteurs(expediteurs: list[str]) -> str:
    """FROM a OR FROM b ... en syntaxe IMAP préfixée : (OR (FROM a) (FROM b))."""
    termes = [f'FROM "{e}"' for e in expediteurs if e.strip()]
    if not termes:
        return ""
    critere = termes[-1]
    for terme in reversed(termes[:-1]):
        critere = f"OR {terme} {critere}"
    return critere


def synchroniser(db: Session, params: Parametres, fabrique: FabriqueClient = _client_ssl) -> list[SyncLog]:
    """Synchronise toutes les boîtes actives, l'une après l'autre (un journal par boîte)."""
    if not _verrou.acquire(blocking=False):
        raise ErreurImap("Une synchronisation est déjà en cours.")
    try:
        comptes = comptes_actifs(db)
        if not comptes:
            journal = SyncLog(
                debut=utcnow(),
                fin=utcnow(),
                nb_mails=0,
                erreur="Aucune boîte mail configurée (Paramètres → Mails).",
            )
            db.add(journal)
            db.commit()
            return [journal]
        return [_synchroniser_compte(db, params, c, fabrique) for c in comptes]
    finally:
        _verrou.release()


def _synchroniser_compte(
    db: Session, params: Parametres, compte: CompteVinted, fabrique: FabriqueClient
) -> SyncLog:
    journal = SyncLog(debut=utcnow(), nb_mails=0, compte_id=compte.id)
    db.add(journal)
    db.commit()
    # Compteurs locaux : un rollback (mail en erreur) ne doit pas les remettre à zéro.
    nouveaux = 0
    erreur: str | None = None
    try:
        cfg = config_depuis(compte)
        depuis = (
            (compte.derniere_synchro - timedelta(days=1))
            if compte.derniere_synchro
            else (utcnow() - timedelta(days=PREMIERE_SYNCHRO_JOURS))
        )
        client = _ouvrir(cfg, fabrique)
        erreurs: list[str] = []
        try:
            criteres = (
                f"SINCE {date_imap(depuis)} {critere_expediteurs(params.expediteurs_vinted or [])}".strip()
            )
            statut, donnees = client.uid("SEARCH", None, criteres)
            if statut != "OK":
                raise ErreurImap("La recherche des mails a échoué sur le serveur.")
            uids = donnees[0].split() if donnees and donnees[0] else []
            for uid in uids:
                try:
                    statut, contenu = client.uid("FETCH", uid, "(BODY.PEEK[])")
                    brut = next((c[1] for c in contenu if isinstance(c, tuple) and len(c) > 1), None)
                    if statut != "OK" or not isinstance(brut, bytes):
                        continue
                    if enregistrer_mail(db, lire_mail(brut), compte_id=compte.id) is not None:
                        nouveaux += 1
                except Exception as exc:  # un mail illisible ne bloque pas les autres
                    db.rollback()
                    annuler_en_attente(db)
                    erreurs.append(f"Mail {uid.decode(errors='ignore')} : {type(exc).__name__}")
                    log.warning(
                        "sync_mail_erreur", uid=uid.decode(errors="ignore"), erreur=type(exc).__name__
                    )
        finally:
            _fermer(client)
        compte.derniere_synchro = journal.debut
        erreur = "\n".join(erreurs[:20]) or None
    except (ErreurImap, crypto.CleManquante) as exc:
        db.rollback()
        erreur = str(exc)
    finally:
        journal.nb_mails = nouveaux
        journal.erreur = erreur
        journal.fin = utcnow()
        db.add(journal)
        db.commit()
    log.info("sync_imap", compte=compte.id, nb_mails=journal.nb_mails, erreur=bool(journal.erreur))
    return journal
