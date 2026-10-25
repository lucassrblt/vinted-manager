import base64
import io
import json
import zipfile
from datetime import timedelta
from decimal import Decimal as D
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pywebpush import WebPushException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import scheduler
from app.config import get_settings
from app.db import utcnow
from app.models import AbonnementPush, Article, Envoi, Utilisateur, Vente
from app.seed.demo import installer_demo
from app.services import push, traitement
from app.services.email_parser import lire_mail
from app.services.traitement import enregistrer_mail
from tests import mails_synthetiques as ms

ABONNEMENT = {"endpoint": "https://push.example.com/abc123", "keys": {"p256dh": "B" * 87, "auth": "A" * 22}}


@pytest.fixture
def envois(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Clés VAPID de test et capture des envois (aucun appel réseau)."""
    publique, privee = push.generer_cles()
    monkeypatch.setattr(get_settings(), "vapid_public_key", publique)
    monkeypatch.setattr(get_settings(), "vapid_private_key", privee)
    captures: list[dict[str, Any]] = []
    monkeypatch.setattr(push, "webpush", lambda **kw: captures.append(kw))
    # Les mails synthétiques sont datés du 20/10/2026 : ils doivent rester « récents » pour notifier.
    monkeypatch.setattr(traitement, "AGE_MAX_NOTIFICATION_JOURS", 100_000)
    return captures


def test_cles_vapid_au_bon_format() -> None:
    publique, privee = push.generer_cles()
    assert len(base64.urlsafe_b64decode(publique + "==")) == 65  # point non compressé P-256
    assert len(base64.urlsafe_b64decode(privee + "=")) == 32


def test_abonnement_et_notification_de_test(client: TestClient, envois: list[dict[str, Any]]) -> None:
    assert client.get("/api/push/config").json()["configure"] is True
    r = client.post("/api/push/abonnements", json=ABONNEMENT, headers={"user-agent": "iPhone Safari"})
    assert r.status_code == 201 and r.json()["user_agent"] == "iPhone Safari"
    assert (
        client.post("/api/push/abonnements", json=ABONNEMENT).status_code == 201
    )  # ré-abonnement idempotent
    assert len(client.get("/api/push/abonnements").json()) == 1
    assert client.post("/api/push/test").json() == {"appareils": 1}
    message = json.loads(envois[0]["data"])
    assert message["titre"] == "Notification de test" and envois[0]["vapid_claims"]["sub"].startswith(
        "mailto:"
    )
    assert client.delete(f"/api/push/abonnements/{r.json()['id']}").status_code == 204
    assert client.post("/api/push/test").status_code == 409


def test_sans_cles_vapid(client: TestClient) -> None:
    assert client.post("/api/push/test").status_code == 409


def test_vente_detectee_notifie_apres_commit(db: Session, regles: None, envois: list[dict[str, Any]]) -> None:
    db.add(AbonnementPush(endpoint=ABONNEMENT["endpoint"], p256dh="x" * 20, auth="y" * 10))
    db.add(
        Article(
            nom="Pull demi-zip polaire Ralph Lauren - Noir",
            prix_achat_net=D("16.67"),
            prix_vente_cible=D("45"),
            statut="en_ligne",
        )
    )
    db.commit()
    enregistrer_mail(db, lire_mail(ms.VENTE))
    assert [json.loads(e["data"])["titre"] for e in envois] == [
        "🛍️ Vendu : Pull demi-zip polaire Ralph Lauren - Noir"
    ]
    enregistrer_mail(db, lire_mail(ms.LITIGE))
    assert json.loads(envois[-1]["data"])["titre"] == "Nouveau litige"


def test_vieux_mails_ne_notifient_pas(
    db: Session, regles: None, envois: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(traitement, "AGE_MAX_NOTIFICATION_JOURS", 2)
    db.add(AbonnementPush(endpoint=ABONNEMENT["endpoint"], p256dh="x" * 20, auth="y" * 10))
    db.add(
        Article(nom="Pull demi-zip polaire Ralph Lauren - Noir", prix_vente_cible=D("45"), statut="en_ligne")
    )
    db.commit()
    vieux = ms.mail(
        "Ton article a été vendu !",
        "claire_75 a acheté ton article « Pull demi-zip polaire Ralph Lauren - Noir ».\nPrix : 45,00 €",
        date=utcnow() - timedelta(days=10),
    )
    assert enregistrer_mail(db, lire_mail(vieux)) is not None
    assert db.scalar(select(func.count(Vente.id))) == 1 and envois == []


def test_preferences_desactivent_un_type(
    client: TestClient, db: Session, regles: None, envois: list[dict[str, Any]]
) -> None:
    db.add(AbonnementPush(endpoint=ABONNEMENT["endpoint"], p256dh="x" * 20, auth="y" * 10))
    db.commit()
    prefs = client.get("/api/parametres/notifications").json()
    assert prefs == {
        "vente": True,
        "litige": True,
        "offre": True,
        "message": True,
        "favori": True,
        "non_classe": True,
        "rappel_envois": True,
    }
    client.put("/api/parametres/notifications", json=prefs | {"offre": False})
    enregistrer_mail(db, lire_mail(ms.OFFRE))
    assert envois == []


def _abonne(db: Session) -> None:
    db.add(AbonnementPush(endpoint=ABONNEMENT["endpoint"], p256dh="x" * 20, auth="y" * 10))
    db.commit()


def _derniere(envois: list[dict[str, Any]]) -> dict[str, Any]:
    return json.loads(envois[-1]["data"])


def test_offre_detaillee(db: Session, regles: None, envois: list[dict[str, Any]]) -> None:
    _abonne(db)
    db.add(
        Article(
            nom="Pull demi-zip polaire Ralph Lauren - Tibet",
            prix_achat_net=D("10"),
            prix_vente_cible=D("40"),
            statut="en_ligne",
        )
    )
    db.commit()
    enregistrer_mail(db, lire_mail(ms.OFFRE))
    notif = _derniere(envois)
    assert notif["titre"] == "💰 Offre de 35 € sur Pull demi-zip polaire Ralph Lauren - Tibet"
    assert notif["corps"].startswith("Affiché 40 € (−12 %) · conseil : ")
    assert notif["url"] == "/messages"


def test_offre_reelle_dans_commande(db: Session, regles: None, envois: list[dict[str, Any]]) -> None:
    _abonne(db)
    titre = "Sweat demi-zip Polo Ralph Lauren gris chiné taille M"
    db.add(Article(nom=titre, prix_achat_net=D("15"), prix_vente_cible=D("45"), statut="en_ligne"))
    db.commit()
    offre = ms.mail(
        f"Commande mise à jour pour {titre}",
        "Bonjour vendeur,\nlea_92 te propose d'acheter ton article.\n"
        "Bonjour, accepterais-tu de me vendre ceci à 30,00 € ?\n",
    )
    enregistrer_mail(db, lire_mail(offre))
    notif = _derniere(envois)
    assert notif["titre"] == f"💰 Offre de 30 € sur {titre}"
    assert "Affiché 45 € (−33 %)" in notif["corps"] and notif["corps"].endswith("lea_92")


def test_offre_reelle_prix_en_tete(db: Session, regles: None, envois: list[dict[str, Any]]) -> None:
    """Format réel du 22/10/2026 : « €12.00 au lieu de €18.00 », article absent du stock."""
    _abonne(db)
    offre = ms.mail(
        "Nouvelle offre pour Sweat à capuche adidas gris chiné taille L",
        "vendeur,\nsilvigarbin te propose d'acheter Sweat à capuche adidas gris chiné taille L à un prix "
        "plus bas.\n€12.00\nNouvelle offre :\n€12.00 au lieu de €18.00\nRépondre à l'offre\n",
    )
    enregistrer_mail(db, lire_mail(offre))
    assert _derniere(envois) == {
        "titre": "💰 Offre de 12 € sur Sweat à capuche adidas gris chiné taille L",
        "corps": "Affiché 18 € (−33 %) · silvigarbin",
        "url": "/messages",
    }


def test_message_et_favori_notifient(db: Session, regles: None, envois: list[dict[str, Any]]) -> None:
    _abonne(db)
    bonnet = Article(nom="Bonnet Ralph Lauren - Blanc", prix_vente_cible=D("16"), statut="en_ligne")
    db.add(bonnet)
    db.commit()
    enregistrer_mail(db, lire_mail(ms.MESSAGE))
    assert _derniere(envois)["titre"] == "💬 Message de tom_r"
    assert _derniere(envois)["corps"] == "Bonnet Ralph Lauren - Blanc"
    favori = ms.mail(
        "Quelqu'un a marqué ton article comme favori",
        "nina_33 a marqué ton article « Bonnet Ralph Lauren - Blanc » comme favori.",
    )
    email = enregistrer_mail(db, lire_mail(favori))
    assert email is not None and email.type_detecte == "favori" and email.article_id == bonnet.id
    assert _derniere(envois) == {
        "titre": "❤️ Nouveau favori",
        "corps": "Bonnet Ralph Lauren - Blanc · 16 €",
        "url": f"/stock/{bonnet.id}",
    }


def test_mail_vinted_non_reconnu_notifie(db: Session, regles: None, envois: list[dict[str, Any]]) -> None:
    _abonne(db)
    enregistrer_mail(db, lire_mail(ms.INCONNU))
    assert _derniere(envois)["titre"] == "Mail Vinted non reconnu"
    assert _derniere(envois)["corps"] == "Les tendances de la semaine"


def test_abonnement_expire_supprime(
    db: Session, envois: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch
) -> None:
    class Reponse:
        status_code = 410

    def expire(**kw: Any) -> None:
        raise WebPushException("Gone", response=Reponse())

    monkeypatch.setattr(push, "webpush", expire)
    db.add(AbonnementPush(endpoint=ABONNEMENT["endpoint"], p256dh="x" * 20, auth="y" * 10))
    db.commit()
    assert push.envoyer(db, "vente", "Test") == 0
    assert db.scalar(select(func.count(AbonnementPush.id))) == 0


def test_rappel_de_9h(db: Session, envois: list[dict[str, Any]], monkeypatch: pytest.MonkeyPatch) -> None:
    from app import db as module_db

    monkeypatch.setattr(scheduler, "SessionLocal", module_db.SessionLocal)
    db.add(AbonnementPush(endpoint=ABONNEMENT["endpoint"], p256dh="x" * 20, auth="y" * 10))
    from datetime import datetime, time
    from zoneinfo import ZoneInfo

    # Midi à Paris aujourd'hui : stable quelle que soit l'heure d'exécution du test.
    midi = datetime.combine(datetime.now(ZoneInfo("Europe/Paris")).date(), time(12), ZoneInfo("Europe/Paris"))
    for decalage, statut in (
        (timedelta(0), "a_imprimer"),
        (-timedelta(days=2), "imprime"),
        (timedelta(days=4), "a_imprimer"),
        (timedelta(0), "depose"),
    ):
        a = Article(nom="A", statut="vendu", prix_achat_net=D("5"))
        db.add(a)
        db.flush()
        v = Vente(article_id=a.id, prix=D("10"), date_heure=utcnow())
        db.add(v)
        db.flush()
        db.add(Envoi(vente_id=v.id, statut=statut, date_limite_envoi=midi + decalage))
    db.commit()
    scheduler.tache_rappel_envois()
    contenu = json.loads(envois[0]["data"])
    assert (
        contenu["titre"] == "2 colis à envoyer"
        and "en retard" in contenu["corps"]
        and contenu["url"] == "/envois"
    )


def test_sauvegarde_complete_sans_secrets(client: TestClient, db: Session) -> None:
    from app.api.deps import get_parametres
    from app.models import CompteVinted
    from app.services import crypto

    get_parametres(db)
    db.add(
        CompteVinted(
            nom="Perso",
            imap_serveur="imap.gmail.com",
            imap_email="moi@gmail.com",
            imap_mot_de_passe_chiffre=crypto.chiffrer("secret-imap"),
        )
    )
    db.add(Article(nom="Pull", prix_achat_net=D("10")))
    db.commit()
    client.post(
        "/api/preuves",
        data={"article_id": "1"},
        files={"fichier": ("f.pdf", ms.pdf_vierge(), "application/pdf")},
    )
    r = client.get("/api/backup/complet.zip")
    assert r.status_code == 200
    z = zipfile.ZipFile(io.BytesIO(r.content))
    noms = z.namelist()
    assert any(n.endswith(".xlsx") for n in noms) and "base.json" in noms
    assert any(n.startswith("fichiers/preuves/") for n in noms)
    base = json.loads(z.read("base.json"))
    assert base["article"][0]["nom"] == "Pull"
    assert "mot_de_passe_hash" not in base["utilisateur"][0]
    assert base["compte_vinted"][0]["imap_email"] == "moi@gmail.com"
    assert "imap_mot_de_passe_chiffre" not in base["compte_vinted"][0]
    assert "session_utilisateur" not in base


def test_seed_demo(db: Session) -> None:
    resume = installer_demo(db)
    assert resume["batches"] == 4 and resume["articles"] > 30 and resume["ventes"] > 0
    with pytest.raises(ValueError):
        installer_demo(db)
    assert db.scalar(select(func.count(Utilisateur.id))) == 0  # la démo ne crée pas de compte
