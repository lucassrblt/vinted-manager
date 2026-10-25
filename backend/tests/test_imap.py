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
from app.models import Article, CompteVinted, EmailVinted, SyncLog
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
            mail = self.mails[int(args[0]) - 1]
            if args[1] == "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID)])":
                entete = b"".join(
                    ligne for ligne in mail.splitlines(True) if ligne.lower().startswith(b"message-id:")
                )
                return "OK", [(b"1 (BODY[HEADER.FIELDS (MESSAGE-ID)] {n}", entete + b"\r\n"), b")"]
            assert args[1] == "(BODY.PEEK[])", "les mails doivent être lus sans être marqués comme lus"
            return "OK", [(b"1 (BODY[] {n}", mail), b")"]
        raise AssertionError(f"Commande interdite : {commande}")

    def store(self, *a: Any) -> None:
        raise AssertionError("STORE interdit (marquerait les mails)")

    def expunge(self, *a: Any) -> None:
        raise AssertionError("EXPUNGE interdit")

    def logout(self) -> None:
        pass


def _configurer(db: Session, email: str = "moi@gmail.com", nom: str = "Perso") -> CompteVinted:
    compte = CompteVinted(
        nom=nom,
        imap_serveur="imap.gmail.com",
        imap_port=993,
        imap_email=email,
        imap_mot_de_passe_chiffre=crypto.chiffrer("abcd efgh ijkl mnop"),
    )
    db.add(compte)
    get_parametres(db).expediteurs_vinted = ["vinted.fr", "vinted.com"]
    db.commit()
    return compte


def test_synchro_lecture_seule_et_dedoublonnage(db: Session, regles: None) -> None:
    compte = _configurer(db)
    faux = FauxImap([ms.VENTE, ms.ARGENT, ms.INCONNU])
    [journal] = imap_sync.synchroniser(db, get_parametres(db), lambda *_: faux)
    assert journal.erreur is None and journal.nb_mails == 3 and journal.compte_id == compte.id
    assert faux.readonly is True
    recherche = next(c for c in faux.commandes if c[0] == "SEARCH")
    assert 'OR FROM "vinted.fr" FROM "vinted.com"' in recherche[-1] and "SINCE" in recherche[-1]
    # Deuxième passage : mêmes mails, rien de nouveau, et seul l'en-tête Message-ID est relu
    deuxieme = FauxImap([ms.VENTE, ms.ARGENT, ms.INCONNU])
    [journal] = imap_sync.synchroniser(db, get_parametres(db), lambda *_: deuxieme)
    assert journal.nb_mails == 0
    assert all(c[2] != "(BODY.PEEK[])" for c in deuxieme.commandes if c[0] == "FETCH")
    assert db.scalar(select(func.count(EmailVinted.id))) == 3
    assert set(db.scalars(select(EmailVinted.compte_id))) == {compte.id}
    db.refresh(compte)
    assert compte.derniere_synchro is not None and compte.derniere_synchro > utcnow() - timedelta(minutes=1)


def test_synchro_mail_illisible_ne_bloque_pas(db: Session, regles: None) -> None:
    _configurer(db)
    [journal] = imap_sync.synchroniser(
        db, get_parametres(db), lambda *_: FauxImap([b"\x00\xff pas un mail", ms.ARGENT])
    )
    assert db.scalar(select(func.count(EmailVinted.id))) >= 1
    assert journal.fin is not None


def test_message_clair_gmail(db: Session) -> None:
    cfg = imap_sync.ConfigImap("imap.gmail.com", 993, "moi@gmail.com", "mauvais")
    faux = FauxImap([], erreur_login="[AUTHENTICATIONFAILED] Invalid credentials (Failure)")
    with pytest.raises(imap_sync.ErreurImap, match="mot de passe d'application"):
        imap_sync.tester_connexion(cfg, lambda *_: faux)


def test_message_clair_adresse_gmail_inconnue() -> None:
    cfg = imap_sync.ConfigImap("imap.gmail.com", 993, "inconnu@gmail.com", "x")
    faux = FauxImap([], erreur_login="b'Lookup failed 5c2dc87 mb3963'")
    with pytest.raises(imap_sync.ErreurImap, match="ne connaît pas l'adresse inconnu@gmail.com"):
        imap_sync.tester_connexion(cfg, lambda *_: faux)


def test_synchro_non_configuree_journalisee(db: Session) -> None:
    [journal] = imap_sync.synchroniser(db, get_parametres(db), lambda *_: FauxImap([]))
    assert journal.erreur is not None and "configurée" in journal.erreur
    assert db.scalar(select(func.count(SyncLog.id))) == 1


def test_comptes_mot_de_passe_chiffre(client: TestClient, db: Session) -> None:
    corps = {
        "nom": "Perso",
        "serveur": "imap.gmail.com",
        "port": 993,
        "email": "moi@gmail.com",
        "mot_de_passe": "secret-app",
        "dossier": "INBOX",
    }
    r = client.post("/api/comptes", json=corps)
    assert r.status_code == 201, r.text
    assert "secret" not in r.text
    id_compte = r.json()["id"]
    compte = db.get(CompteVinted, id_compte)
    assert compte is not None and "secret-app" not in compte.imap_mot_de_passe_chiffre
    assert crypto.dechiffrer(compte.imap_mot_de_passe_chiffre) == "secret-app"
    # Sans mot de passe : l'ancien est conservé
    r = client.put(f"/api/comptes/{id_compte}", json=corps | {"mot_de_passe": None, "dossier": "Vinted"})
    assert r.status_code == 200 and r.json()["imap_dossier"] == "Vinted"
    db.refresh(compte)
    assert crypto.dechiffrer(compte.imap_mot_de_passe_chiffre) == "secret-app"
    # Même adresse branchée deux fois : refusé ; création sans mot de passe : refusée
    assert (
        client.post("/api/comptes", json=corps | {"nom": "Bis", "email": "MOI@gmail.com"}).status_code == 409
    )
    assert (
        client.post("/api/comptes", json=corps | {"email": "b@gmail.com", "mot_de_passe": None}).status_code
        == 422
    )
    config = client.get("/api/parametres/mails").json()
    assert [c["nom"] for c in config["comptes"]] == ["Perso"] and "gmail" in config["presets"]


def test_deux_comptes_synchronises_et_rapproches_separement(
    client: TestClient, db: Session, regles: None
) -> None:
    perso = _configurer(db, "perso@gmail.com", "Perso")
    pro = _configurer(db, "pro@gmail.com", "Pro")
    # Le même pull est en vente sur les deux comptes : chaque vente va à l'exemplaire de son compte.
    nom = "Pull demi-zip polaire Ralph Lauren - Noir"
    pull_perso = Article(nom=nom, prix_vente_cible=45, statut="en_ligne", compte_id=perso.id)
    pull_pro = Article(nom=nom, prix_vente_cible=45, statut="en_ligne", compte_id=pro.id)
    db.add_all([pull_perso, pull_pro])
    db.commit()
    vente_pro = ms.mail(
        "Ton article a été vendu !",
        f"Bonne nouvelle ! marc_92 a acheté ton article « {nom} ».\nPrix : 45,00 €\nCommande n° 99",
        message_id="<vente-pro@vinted.fr>",
    )
    boites = {"perso@gmail.com": [ms.ARGENT], "pro@gmail.com": [vente_pro]}

    # Chaque connexion sert la boîte de l'adresse utilisée.
    originale = FauxImap.login

    def login(self: FauxImap, email: str, mdp: str) -> None:
        self.mails = boites[email]
        originale(self, email, mdp)

    FauxImap.login = login  # type: ignore[method-assign]
    try:
        journaux = imap_sync.synchroniser(db, get_parametres(db), lambda *_: FauxImap([]))
    finally:
        FauxImap.login = originale  # type: ignore[method-assign]
    assert [(j.compte_id, j.nb_mails, j.erreur) for j in journaux] == [(perso.id, 1, None), (pro.id, 1, None)]
    db.refresh(pull_perso)
    db.refresh(pull_pro)
    assert pull_pro.statut == "vendu" and pull_perso.statut == "en_ligne"
    mails = client.get("/api/emails").json()["items"]
    assert {m["compte"] for m in mails} == {"Perso", "Pro"}
    assert client.get(f"/api/emails?compte={pro.id}").json()["total"] == 1
    assert client.get(f"/api/articles?compte_id={pro.id}").json()["total"] == 1
    # Débrancher une boîte conserve ses mails et ses articles
    assert client.delete(f"/api/comptes/{pro.id}").status_code == 204
    assert db.scalar(select(func.count(EmailVinted.id))) == 2
    db.refresh(pull_pro)
    assert pull_pro.compte_id is None


def test_vente_attribue_le_compte_a_l_article(db: Session, regles: None) -> None:
    from app.services.email_parser import lire_mail
    from app.services.traitement import enregistrer_mail

    compte = _configurer(db)
    pull = Article(nom="Pull demi-zip polaire Ralph Lauren - Noir", prix_vente_cible=45, statut="en_ligne")
    db.add(pull)
    db.commit()
    enregistrer_mail(db, lire_mail(ms.VENTE), compte_id=compte.id)
    db.refresh(pull)
    assert pull.statut == "vendu" and pull.compte_id == compte.id


def test_premiere_synchro_remonte_au_premier_achat(db: Session) -> None:
    from datetime import date

    assert imap_sync.debut_historique(db) < utcnow() - timedelta(days=29)
    db.add(Article(nom="Ancien", date_achat=date(2026, 3, 1)))
    db.commit()
    debut = imap_sync.debut_historique(db)
    assert debut.date() == date(2026, 2, 14)  # premier achat moins 15 jours


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
