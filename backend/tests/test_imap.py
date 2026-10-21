import imaplib
import io
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_parametres
from app.db import utcnow
from app.models import EmailVinted, SyncLog
from app.services import bordereaux, crypto, imap_sync
from tests import mails_synthetiques as ms


class FauxImap:
    """Serveur IMAP factice : refuse toute commande qui modifierait la boîte."""

    def __init__(self, mails: list[bytes], erreur_login: str | None = None) -> None:
        self.mails = mails
        self.erreur_login = erreur_login
        self.commandes: list[tuple[str, ...]] = []
        self.readonly: bool | None = None

    def login(self, email: str, mdp: str) -> None:
        if self.erreur_login:
            raise imaplib.IMAP4.error(self.erreur_login)

    def select(self, dossier: str, readonly: bool = False) -> tuple[str, list[bytes]]:
        self.readonly = readonly
        return "OK", [str(len(self.mails)).encode()]

    def uid(self, commande: str, *args: Any) -> tuple[str, list[Any]]:
        self.commandes.append((commande, *[str(a) for a in args]))
        if commande == "SEARCH":
            return "OK", [b" ".join(str(i + 1).encode() for i in range(len(self.mails)))]
        if commande == "FETCH":
            assert args[1] == "(BODY.PEEK[])", "les mails doivent être lus sans être marqués comme lus"
            return "OK", [(b"1 (BODY[] {n}", self.mails[int(args[0]) - 1]), b")"]
        raise AssertionError(f"Commande interdite : {commande}")

    def store(self, *a: Any) -> None:
        raise AssertionError("STORE interdit (marquerait les mails)")

    def expunge(self, *a: Any) -> None:
        raise AssertionError("EXPUNGE interdit")

    def logout(self) -> None:
        pass


def _configurer(db: Session) -> None:
    p = get_parametres(db)
    p.imap_serveur, p.imap_port, p.imap_email = "imap.gmail.com", 993, "moi@gmail.com"
    p.imap_mot_de_passe_chiffre = crypto.chiffrer("abcd efgh ijkl mnop")
    p.expediteurs_vinted = ["vinted.fr", "vinted.com"]
    db.commit()


def test_synchro_lecture_seule_et_dedoublonnage(db: Session, regles: None) -> None:
    _configurer(db)
    faux = FauxImap([ms.VENTE, ms.ARGENT, ms.INCONNU])
    journal = imap_sync.synchroniser(db, get_parametres(db), lambda *_: faux)
    assert journal.erreur is None and journal.nb_mails == 3
    assert faux.readonly is True
    recherche = next(c for c in faux.commandes if c[0] == "SEARCH")
    assert 'OR FROM "vinted.fr" FROM "vinted.com"' in recherche[-1] and "SINCE" in recherche[-1]
    # Deuxième passage : mêmes mails, rien de nouveau
    journal = imap_sync.synchroniser(
        db, get_parametres(db), lambda *_: FauxImap([ms.VENTE, ms.ARGENT, ms.INCONNU])
    )
    assert journal.nb_mails == 0
    assert db.scalar(select(func.count(EmailVinted.id))) == 3
    params = get_parametres(db)
    assert params.derniere_synchro is not None and params.derniere_synchro > utcnow() - timedelta(minutes=1)


def test_synchro_mail_illisible_ne_bloque_pas(db: Session, regles: None) -> None:
    _configurer(db)
    journal = imap_sync.synchroniser(
        db, get_parametres(db), lambda *_: FauxImap([b"\x00\xff pas un mail", ms.ARGENT])
    )
    assert db.scalar(select(func.count(EmailVinted.id))) >= 1
    assert journal.fin is not None


def test_message_clair_gmail(db: Session) -> None:
    cfg = imap_sync.ConfigImap("imap.gmail.com", 993, "moi@gmail.com", "mauvais")
    faux = FauxImap([], erreur_login="[AUTHENTICATIONFAILED] Invalid credentials (Failure)")
    with pytest.raises(imap_sync.ErreurImap, match="mot de passe d'application"):
        imap_sync.tester_connexion(cfg, lambda *_: faux)


def test_synchro_non_configuree_journalisee(db: Session) -> None:
    journal = imap_sync.synchroniser(db, get_parametres(db), lambda *_: FauxImap([]))
    assert journal.erreur is not None and "configurée" in journal.erreur
    assert db.scalar(select(func.count(SyncLog.id))) == 1


def test_config_imap_mot_de_passe_chiffre(client: TestClient, db: Session) -> None:
    corps = {
        "serveur": "imap.gmail.com",
        "port": 993,
        "email": "moi@gmail.com",
        "mot_de_passe": "secret-app",
        "dossier": "INBOX",
    }
    r = client.put("/api/parametres/imap", json=corps)
    assert r.status_code == 200 and r.json()["mot_de_passe_defini"] is True
    assert "secret" not in r.text
    p = get_parametres(db)
    db.refresh(p)
    assert p.imap_mot_de_passe_chiffre and "secret-app" not in p.imap_mot_de_passe_chiffre
    assert crypto.dechiffrer(p.imap_mot_de_passe_chiffre) == "secret-app"
    # Sans mot de passe : l'ancien est conservé
    r = client.put("/api/parametres/imap", json=corps | {"mot_de_passe": None, "dossier": "Vinted"})
    assert r.json()["dossier"] == "Vinted" and r.json()["mot_de_passe_defini"] is True


def test_critere_expediteurs() -> None:
    assert imap_sync.critere_expediteurs(["a"]) == 'FROM "a"'
    assert imap_sync.critere_expediteurs(["a", "b", "c"]) == 'OR FROM "a" OR FROM "b" FROM "c"'


# --- Bordereaux -------------------------------------------------------------------------------


def test_fusion_et_format_10x15() -> None:
    pdf = bordereaux.fusionner([ms.pdf_vierge(), ms.pdf_vierge(842, 595)])
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 2
    pages = PdfReader(
        io.BytesIO(bordereaux.fusionner([ms.pdf_vierge(), ms.pdf_vierge(842, 595)], format_10x15=True))
    ).pages
    for page in pages:
        assert round(float(page.mediabox.width)) == 283 and round(float(page.mediabox.height)) == 425


def test_telechargement_bordereaux_et_statut_imprime(client: TestClient, db: Session, regles: None) -> None:
    from tests.test_traitement import _article, _recevoir

    _article(db, "Pull demi-zip polaire Ralph Lauren - Noir")
    _recevoir(db, ms.VENTE)
    _recevoir(db, ms.BORDEREAU)
    envoi = client.get("/api/envois").json()["envois"][0]
    r = client.get(
        "/api/envois/bordereaux.pdf",
        params={"ids": [envoi["id"]], "format": "10x15", "marquer_imprimes": True},
    )
    assert r.status_code == 200 and r.content.startswith(b"%PDF")
    assert client.get("/api/envois").json()["envois"][0]["statut"] == "imprime"
    r = client.patch(f"/api/envois/{envoi['id']}", json={"statut": "depose", "transporteur": "Mondial Relay"})
    assert r.json()["statut"] == "depose" and r.json()["article"]["statut"] == "envoye"


# --- Règles -----------------------------------------------------------------------------------


def test_regles_crud_validation_et_reapplication(client: TestClient, db: Session, regles: None) -> None:
    from tests.test_traitement import _recevoir

    email = _recevoir(db, ms.INCONNU)
    suggestion = client.post(f"/api/emails/{email.id}/suggestion-regle").json()
    assert suggestion["conditions"]["expediteurs"] == ["vinted.fr"]
    assert suggestion["conditions"]["sujet_contient"] == ["tendances"]

    invalide = {"nom": "x", "type_cible": "autre", "conditions": {"corps_regex": "("}}
    assert client.post("/api/regles", json=invalide).status_code == 422
    assert client.post("/api/regles", json={"nom": "vide", "type_cible": "autre"}).status_code == 422

    regle = {
        "nom": "Newsletter",
        "type_cible": "autre",
        "priorite": 5,
        "conditions": suggestion["conditions"],
    }
    test = client.post("/api/regles/tester", json=regle).json()
    assert test["nb_correspondances"] == 1
    assert client.post("/api/regles", json=regle).status_code == 201
    assert client.post("/api/regles/reappliquer").json() == {"reclasses": 1}
    db.refresh(email)
    assert email.type_detecte == "autre" and email.statut_traitement == "traite"
