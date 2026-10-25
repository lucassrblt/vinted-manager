"""Écoute en temps réel des boîtes mail (IMAP IDLE) : dès qu'un mail arrive, la synchro est lancée.

Une connexion par boîte active, ouverte en lecture seule comme la synchro. La synchro planifiée
reste le filet de sécurité : si l'écoute tombe, le mail est lu au passage suivant.
"""

import contextlib
import socket
import threading
import time
from collections.abc import Callable
from typing import Any

from app.db import SessionLocal
from app.logging import log
from app.models import CompteVinted
from app.services import imap_sync

# Gmail coupe un IDLE au bout de ~29 min : la connexion est renouvelée bien avant.
DUREE_IDLE_SECONDES = 9 * 60
# Attente avant de se reconnecter après une erreur (croissante, puis plafonnée).
ATTENTES_ERREUR = (30, 60, 120, 300)
# Si une synchro est déjà en cours, on réessaie un peu plus tard pour ne pas rater le mail.
ESSAIS_SYNCHRO = 6
PAUSE_SYNCHRO_SECONDES = 5

_ecouteurs: dict[int, "Ecouteur"] = {}


def attendre_nouveau_mail(client: Any, delai: float) -> bool:
    """Envoie IDLE et attend au plus `delai` secondes. True si un mail est arrivé (EXISTS) : la
    connexion reste alors utilisable. False si le délai est écoulé : la connexion doit être fermée
    (après un dépassement de délai, la lecture n'est plus fiable)."""
    tag = client._new_tag()
    client.send(tag + b" IDLE\r\n")
    reponse = client.readline()
    if not reponse.startswith(b"+"):
        raise imap_sync.ErreurImap(f"Le serveur refuse l'écoute (IDLE) : {reponse[:100]!r}")
    client.sock.settimeout(delai)
    try:
        while True:
            ligne = client.readline()
            if not ligne:
                raise ConnectionError("Connexion fermée par le serveur.")
            if ligne.rstrip().upper().endswith(b"EXISTS"):
                break
    except TimeoutError:
        return False
    client.sock.settimeout(imap_sync.TIMEOUT_SECONDES)
    client.send(b"DONE\r\n")
    while not client.readline().startswith(tag):
        pass
    return True


def declencher_synchro(synchroniser: Callable[[], bool]) -> None:
    """Lance la synchro ; si une autre est en cours, réessaie quelques secondes plus tard."""
    for _ in range(ESSAIS_SYNCHRO):
        if synchroniser():
            return
        time.sleep(PAUSE_SYNCHRO_SECONDES)


def empreinte(compte: CompteVinted) -> tuple[Any, ...]:
    """Ce qui oblige à rouvrir la connexion quand ça change."""
    return (
        compte.imap_serveur,
        compte.imap_port,
        compte.imap_email,
        compte.imap_mot_de_passe_chiffre,
        compte.imap_dossier,
    )


class Ecouteur(threading.Thread):
    def __init__(
        self,
        compte_id: int,
        signature: tuple[Any, ...],
        synchroniser: Callable[[], bool],
        fabrique: imap_sync.FabriqueClient,
    ) -> None:
        super().__init__(daemon=True, name=f"imap-idle-{compte_id}")
        self.compte_id = compte_id
        self.signature = signature
        self.synchroniser = synchroniser
        self.fabrique = fabrique
        self.stop = threading.Event()
        self.client: Any = None

    def arreter(self) -> None:
        self.stop.set()
        if self.client is not None:
            with contextlib.suppress(Exception):  # débloque une attente IDLE en cours
                self.client.sock.shutdown(socket.SHUT_RDWR)

    def _config(self) -> imap_sync.ConfigImap | None:
        with SessionLocal() as db:
            compte = db.get(CompteVinted, self.compte_id)
            return imap_sync.config_depuis(compte) if compte is not None and compte.actif else None

    def run(self) -> None:
        echecs = 0
        while not self.stop.is_set():
            try:
                cfg = self._config()
                if cfg is None:
                    return
                self.client = imap_sync.ouvrir(cfg, self.fabrique)
                log.info("ecoute_ouverte", compte=self.compte_id)
                echecs = 0
                try:
                    while not self.stop.is_set() and attendre_nouveau_mail(self.client, DUREE_IDLE_SECONDES):
                        log.info("ecoute_nouveau_mail", compte=self.compte_id)
                        declencher_synchro(self.synchroniser)
                finally:
                    imap_sync.fermer(self.client)
                    self.client = None
            except Exception as exc:
                if self.stop.is_set():
                    return
                attente = ATTENTES_ERREUR[min(echecs, len(ATTENTES_ERREUR) - 1)]
                echecs += 1
                log.warning("ecoute_erreur", compte=self.compte_id, erreur=str(exc)[:200], attente=attente)
                self.stop.wait(attente)


def surveiller(
    synchroniser: Callable[[], bool], fabrique: imap_sync.FabriqueClient = imap_sync.client_ssl
) -> None:
    """Une écoute par boîte active : démarre les manquantes, arrête celles des boîtes retirées ou
    modifiées, relance celles qui se sont arrêtées. Appelé chaque minute par le planificateur."""
    with SessionLocal() as db:
        voulues = {c.id: empreinte(c) for c in imap_sync.comptes_actifs(db)}
    for compte_id, ecouteur in list(_ecouteurs.items()):
        if voulues.get(compte_id) != ecouteur.signature or not ecouteur.is_alive():
            ecouteur.arreter()
            del _ecouteurs[compte_id]
    for compte_id, signature in voulues.items():
        if compte_id not in _ecouteurs:
            ecouteur = Ecouteur(compte_id, signature, synchroniser, fabrique)
            _ecouteurs[compte_id] = ecouteur
            ecouteur.start()


def arreter_tout() -> None:
    for ecouteur in _ecouteurs.values():
        ecouteur.arreter()
    _ecouteurs.clear()
