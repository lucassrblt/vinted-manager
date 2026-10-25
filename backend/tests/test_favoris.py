"""Phase 4 : message et offre aux membres qui mettent une annonce en favori."""

from datetime import timedelta
from decimal import Decimal as D
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, CompteVinted, ConversationVinted, FavoriVinted, JournalVinted, TacheVinted
from app.models.enums import StatutArticle
from app.services import favoris, horaires, telegram
from tests.outils_extension import LUCAS_VINTED, FauxTelegram, a_heure, creer_compte, entetes

ITEM = 10475120267
MEMBRE = 900000005


@pytest.fixture
def lucas(db: Session) -> tuple[CompteVinted, str]:
    compte, jeton = creer_compte(db, "Lucas", LUCAS_VINTED)
    compte.telegram_chat_id = "1001"
    db.commit()
    return compte, jeton


@pytest.fixture
def sweat(db: Session, lucas: tuple[CompteVinted, str]) -> Article:
    a = Article(
        nom="Sweat Uniqlo",
        titre_annonce="Sweat col rond Uniqlo gris chiné taille L",
        statut=StatutArticle.EN_LIGNE,
        compte_id=lucas[0].id,
        prix_vente_cible=D("7"),
        prix_initial=D("7"),
        vinted_item_id=ITEM,
    )
    db.add(a)
    db.commit()
    return a


@pytest.fixture
def telegram_faux(monkeypatch: pytest.MonkeyPatch) -> FauxTelegram:
    faux = FauxTelegram()
    monkeypatch.setattr(telegram, "fabrique", lambda: faux)
    return faux


def notif(
    nid: str, quand: str, membre: int = MEMBRE, item: int = ITEM, pseudo: str = "marie_75"
) -> dict[str, Any]:
    """Format supposé (non capturé) : texte avec « favoris », lien vers l'annonce, identifiant du membre."""
    return {
        "id": nid,
        "body": f"<b>{pseudo}</b> a ajouté ton article <b>Sweat Uniqlo</b> à ses favoris",
        "link": f"https://www.vinted.fr/items/{item}-sweat?referrer=notification",
        "user_id": membre,
        "updated_at": quand,
        "is_read": False,
    }


def iso(minutes: int = 0) -> str:
    return (horaires.maintenant() + timedelta(minutes=minutes)).isoformat()


def evenement(client: TestClient, jeton: str, donnees: dict[str, Any]) -> dict[str, Any]:
    r = client.post(
        "/api/extension/evenements",
        json={"type": "notifications", "donnees": donnees},
        headers=entetes(jeton),
    )
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def initialise(client: TestClient, lucas: tuple[CompteVinted, str], monkeypatch: pytest.MonkeyPatch) -> None:
    a_heure(monkeypatch, 14)
    ancien = notif("n0", iso(-30), membre=1234)
    assert evenement(client, lucas[1], {"notifications": [ancien]}) == {"favoris": 0, "inexploitables": 0}


def test_favori_relance_en_moins_d_une_minute(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str], sweat: Article, initialise: None
) -> None:
    assert evenement(client, lucas[1], {"notifications": [notif("n1", iso())], "source": "api"}) == {
        "favoris": 1,
        "inexploitables": 0,
    }
    f = db.scalars(select(FavoriVinted)).one()
    assert (f.vinted_item_id, f.membre_id, f.membre_login, f.statut, f.montant_offre) == (
        ITEM, MEMBRE, "marie_75", "programme", D("6.50"),
    )  # fmt: skip
    t = db.get(TacheVinted, f.tache_id)
    assert t is not None and (t.type, t.priorite) == ("relance_favori", 2)
    assert t.payload == {
        "item_id": ITEM,
        "membre_id": MEMBRE,
        "login": "marie_75",
        "texte": "Hello, merci pour ton favori ! Je te propose une petite réduction si ça te tente.",
        "montant": "6.5",  # 7 € moins 10 % = 6,30 € → 6,50 €, au-dessus du plancher (6 €)
        "article": "Sweat Uniqlo",
        "favori_id": f.id,
    }
    assert timedelta(seconds=20) <= t.executer_apres - horaires.maintenant() <= timedelta(seconds=60)


def test_un_seul_message_par_membre_et_par_article(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str], sweat: Article, initialise: None
) -> None:
    evenement(client, lucas[1], {"notifications": [notif("n1", iso())]})
    evenement(
        client, lucas[1], {"notifications": [notif("n1", iso()), notif("n2", iso(1))]}
    )  # retire puis remet
    assert len(db.scalars(select(TacheVinted)).all()) == 1


def test_premiere_lecture_et_notifications_ordinaires_ignorees(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str], sweat: Article, initialise: None
) -> None:
    autre = {"id": "n9", "body": "Ton article a été vendu !", "link": f"/items/{ITEM}", "updated_at": iso()}
    assert evenement(client, lucas[1], {"notifications": [autre]}) == {"favoris": 0, "inexploitables": 0}
    assert not db.scalars(select(FavoriVinted)).all()  # le favori « n0 » de la première lecture non plus


def test_favori_inexploitable_signale_une_fois(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    sweat: Article,
    initialise: None,
    telegram_faux: FauxTelegram,
) -> None:
    flou = {"id": "n3", "body": "Quelqu'un a ajouté ton article à ses favoris", "updated_at": iso()}
    assert evenement(client, lucas[1], {"notifications": [flou]}) == {"favoris": 0, "inexploitables": 1}
    evenement(client, lucas[1], {"notifications": [dict(flou, id="n4")]})
    assert len([m for m in telegram_faux.textes() if "Favoris non exploitables" in m]) == 1


def test_favori_la_nuit_traite_a_8_h_s_il_a_moins_de_12_h(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    sweat: Article,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a_heure(monkeypatch, 2)
    evenement(client, lucas[1], {"notifications": []})
    evenement(client, lucas[1], {"notifications": [notif("n1", iso()), notif("n2", iso(-7 * 60), membre=42)]})
    t = db.scalars(select(TacheVinted)).one()
    assert horaires.local(t.executer_apres).hour == 8 and t.payload["membre_id"] == MEMBRE
    ancien = db.scalars(select(FavoriVinted).where(FavoriVinted.membre_id == 42)).one()
    assert ancien.statut == "ignore" and "12 h" in (ancien.raison or "")


def test_pas_de_relance_sans_reduction_possible(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str], sweat: Article, initialise: None
) -> None:
    sweat.prix_initial, sweat.prix_vente_cible = D("10"), D("8.50")  # déjà au plancher (82 % de 10 €)
    db.commit()
    evenement(client, lucas[1], {"notifications": [notif("n1", iso())]})
    f = db.scalars(select(FavoriVinted)).one()
    assert f.statut == "ignore" and "plancher" in (f.raison or "")
    assert not db.scalars(select(TacheVinted)).all()


def test_module_coupe_ou_article_inconnu(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str], sweat: Article, initialise: None
) -> None:
    evenement(client, lucas[1], {"notifications": [notif("n1", iso(), item=123456789)]})
    client.put(f"/api/automatisation/comptes/{lucas[0].id}/reglages", json={"modules": {"favoris": False}})
    evenement(client, lucas[1], {"notifications": [notif("n2", iso())]})
    raisons = sorted(f.raison or "" for f in db.scalars(select(FavoriVinted)))
    assert raisons == ["Annonce non rattachée à un article.", "Module favoris coupé."]


def test_variables_du_message() -> None:
    a = Article(nom="Sweat", titre_annonce="Sweat Uniqlo gris")
    modele = "Hello {prenom}, merci ! {article} à {prix} pour toi ?"
    assert (
        favoris.message(modele, "marie", a, D("6.5"))
        == "Hello marie, merci ! Sweat Uniqlo gris à 6,50 € pour toi ?"
    )
    assert favoris.message(modele, None, a, D("6")) == "Hello, merci ! Sweat Uniqlo gris à 6 € pour toi ?"


def test_extraction_tolerante() -> None:
    n = {
        "id": "x",
        "body": "lea a ajouté ton article à ses favoris",
        "subject_type": "item",
        "subject_id": 55555,
        "sender_id": 777,
    }
    assert favoris.extraire(n, LUCAS_VINTED) == (55555, 777, "lea")
    assert (
        favoris.extraire({"id": "y", "user_id": LUCAS_VINTED, "link": "/items/123456"}, LUCAS_VINTED)[1]
        is None
    )


def test_resultat_relance(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    sweat: Article,
    initialise: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, jeton = lucas
    evenement(client, jeton, {"notifications": [notif("n1", iso()), notif("n2", iso(), membre=43)]})
    resultats = {
        MEMBRE: {"ok": True, "resultat": {"conversation_id": "conv-1", "transaction_id": 23562720554, "offer_id": 1}},
        43: {"ok": False, "erreur": "Conversation non ouverte après 15 s.", "erreur_vinted": False},
    }
    for i in range(2):  # l'ordre dépend des délais tirés au hasard
        a_heure(monkeypatch, 14, 2 + i * 2)
        t = client.get("/api/extension/taches/suivante", headers=entetes(jeton)).json()
        corps = resultats[t["payload"]["membre_id"]]
        client.post(f"/api/extension/taches/{t['id']}/resultat", json=corps, headers=entetes(jeton))
    db.expire_all()
    f1, f2 = db.scalars(select(FavoriVinted).order_by(FavoriVinted.id)).all()
    assert (f1.statut, f1.offre_envoyee, f2.statut, f2.offre_envoyee) == ("relance", True, "erreur", False)
    conv = db.get(ConversationVinted, "conv-1")
    assert conv is not None and conv.dernier_propose == D("6.50") and conv.interlocuteur_id == MEMBRE
    assert conv.article_id == sweat.id and conv.transaction_id == 23562720554
    assert db.scalars(select(JournalVinted).where(JournalVinted.type == "tache_erreur")).first() is not None
    usage = client.get("/api/automatisation/comptes").json()[0]["budget_utilise"]
    assert usage["messages"] == 2 and usage["offres"] == 2  # chaque relance : un message et une offre
