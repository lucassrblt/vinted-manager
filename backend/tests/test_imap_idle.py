import threading
from typing import Any

import pytest
from sqlalchemy.orm import Session

from app.services import imap_idle
from tests.test_imap import _configurer


class FausseSocket:
    def __init__(self) -> None:
        self.delais: list[float] = []
        self.coupee = False

    def settimeout(self, delai: float) -> None:
        self.delais.append(delai)

    def shutdown(self, *_: Any) -> None:
        self.coupee = True


class FauxIdle:
    """Client IMAP factice pour l'écoute : rejoue des lignes reçues du serveur."""

    def __init__(self, lignes: list[bytes | type[BaseException]]) -> None:
        self.lignes = lignes
        self.envoyes: list[bytes] = []
        self.sock = FausseSocket()
        self.readonly: bool | None = None

    def _new_tag(self) -> bytes:
        return b"A001"

    def send(self, donnees: bytes) -> None:
        self.envoyes.append(donnees)

    def readline(self) -> bytes:
        if not self.lignes:
            return b""
        ligne = self.lignes.pop(0)
        if isinstance(ligne, type):
            raise ligne()
        return ligne

    def login(self, *_: Any) -> None:
        pass

    def select(self, dossier: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        self.readonly = readonly
        return "OK", [b"3"]

    def logout(self) -> None:
        pass


def test_nouveau_mail_detecte() -> None:
    client = FauxIdle(
        [b"+ idling\r\n", b"* OK still here\r\n", b"* 4 EXISTS\r\n", b"A001 OK IDLE terminated\r\n"]
    )
    assert imap_idle.attendre_nouveau_mail(client, 540) is True
    assert client.envoyes == [b"A001 IDLE\r\n", b"DONE\r\n"]
    assert client.sock.delais[0] == 540


def test_delai_ecoule_sans_mail() -> None:
    client = FauxIdle([b"+ idling\r\n", TimeoutError])
    assert imap_idle.attendre_nouveau_mail(client, 540) is False
    assert client.envoyes == [b"A001 IDLE\r\n"]  # la connexion sera fermée puis rouverte


def test_idle_refuse() -> None:
    with pytest.raises(imap_idle.imap_sync.ErreurImap, match="IDLE"):
        imap_idle.attendre_nouveau_mail(FauxIdle([b"A001 BAD unknown command\r\n"]), 540)


def test_ecouteur_lance_la_synchro(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    compte = _configurer(db)
    client = FauxIdle([b"+ idling\r\n", b"* 4 EXISTS\r\n", b"A001 OK\r\n"])
    fini = threading.Event()
    appels: list[int] = []

    def synchroniser() -> bool:
        appels.append(1)
        ecouteur.arreter()
        fini.set()
        return True

    ecouteur = imap_idle.Ecouteur(compte.id, (), synchroniser, lambda *_: client)
    ecouteur.start()
    assert fini.wait(5) and appels == [1]
    ecouteur.join(5)
    assert not ecouteur.is_alive() and client.readonly is True


def test_synchro_occupee_reessayee(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(imap_idle, "PAUSE_SYNCHRO_SECONDES", 0)
    reponses = [False, False, True]
    imap_idle.declencher_synchro(lambda: reponses.pop(0))
    assert reponses == []


def test_surveiller_suit_les_comptes(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    demarres: list[int] = []
    monkeypatch.setattr(imap_idle.Ecouteur, "start", lambda self: demarres.append(self.compte_id))
    monkeypatch.setattr(imap_idle.Ecouteur, "is_alive", lambda self: True)
    compte = _configurer(db)
    try:
        imap_idle.surveiller(lambda: True)
        imap_idle.surveiller(lambda: True)
        assert demarres == [compte.id]  # pas de doublon
        compte.imap_email = "autre@gmail.com"  # boîte modifiée : nouvelle connexion
        db.commit()
        imap_idle.surveiller(lambda: True)
        assert demarres == [compte.id, compte.id]
        compte.actif = False
        db.commit()
        imap_idle.surveiller(lambda: True)
        assert imap_idle._ecouteurs == {}
    finally:
        imap_idle.arreter_tout()
