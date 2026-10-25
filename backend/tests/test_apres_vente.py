"""Phase 7 : après-vente (remerciement, récapitulatif de 17 h 30, rappel avant la date limite)."""

import io
from datetime import timedelta
from decimal import Decimal as D
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, CompteVinted, Envoi, JournalVinted, TacheVinted, Vente
from app.models.enums import StatutArticle, StatutEnvoi
from app.services import apres_vente, horaires, push, storage, telegram
from tests.outils_extension import LUCAS_VINTED, FauxTelegram, a_heure, creer_compte, entetes

ITEM = 10495633803


@pytest.fixture
def telegram_faux(monkeypatch: pytest.MonkeyPatch) -> FauxTelegram:
    faux = FauxTelegram()
    monkeypatch.setattr(telegram, "fabrique", lambda: faux)
    monkeypatch.setattr(telegram, "configure", lambda: True)
    return faux


@pytest.fixture
def lucas(db: Session, monkeypatch: pytest.MonkeyPatch) -> tuple[CompteVinted, str]:
    a_heure(monkeypatch, 14)
    compte, jeton = creer_compte(db, "Lucas", LUCAS_VINTED)
    compte.telegram_chat_id = "1001"
    db.commit()
    return compte, jeton


def pdf() -> bytes:
    tampon = io.BytesIO()
    Image.new("RGB", (200, 300), "white").save(tampon, "PDF")
    return tampon.getvalue()


def vendu(
    db: Session,
    compte: CompteVinted | None,
    nom: str = "Sweat Autograph",
    il_y_a: timedelta = timedelta(hours=1),
    **envoi: Any,
) -> Article:
    a = Article(
        nom=nom,
        statut=StatutArticle.VENDU,
        compte_id=compte.id if compte else None,
        vinted_item_id=ITEM,
        prix_vente_reel=D("10"),
    )
    db.add(a)
    db.flush()
    v = Vente(
        article_id=a.id, prix=D("10"), date_heure=horaires.maintenant() - il_y_a, acheteur="membre_test_10"
    )
    db.add(v)
    db.flush()
    db.add(Envoi(vente_id=v.id, statut=StatutEnvoi.A_IMPRIMER, **envoi))
    db.commit()
    return a


def dressing(client: TestClient, jeton: str, items: list[dict[str, Any]], complet: bool = True) -> None:
    r = client.post(
        "/api/extension/evenements",
        json={"type": "dressing", "donnees": {"items": items, "complet": complet}},
        headers=entetes(jeton),
    )
    assert r.status_code == 200, r.text


def remerciements(db: Session) -> list[TacheVinted]:
    return list(db.scalars(select(TacheVinted).where(TacheVinted.type == "message_apres_vente")))


# --- Remerciement --------------------------------------------------------------------------------


def test_vente_confirmee_par_la_disparition_de_l_annonce(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str]
) -> None:
    compte, jeton = lucas
    a = vendu(db, compte)
    dressing(client, jeton, [{"id": ITEM, "title": a.nom, "is_draft": False, "price": {"amount": "10.0"}}])
    assert not remerciements(db)  # encore en ligne : pas confirmée
    dressing(client, jeton, [], complet=False)
    assert not remerciements(db)  # lecture incomplète : on ne conclut rien
    dressing(client, jeton, [])
    t = remerciements(db)[0]
    assert (t.priorite, t.article_id, t.cle) == (3, a.id, f"apres_vente:{t.payload['vente_id']}")
    assert t.payload["acheteur"] == "membre_test_10" and t.payload["item_id"] == ITEM
    assert t.payload["texte"].startswith("Merci beaucoup pour ton achat")
    assert timedelta(minutes=3) <= t.executer_apres - horaires.maintenant() <= timedelta(minutes=10)
    dressing(client, jeton, [])
    assert len(remerciements(db)) == 1


def test_annonce_fermee_vaut_disparition(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str]
) -> None:
    compte, jeton = lucas
    vendu(db, compte)
    dressing(
        client,
        jeton,
        [{"id": ITEM, "title": "x", "is_draft": False, "is_closed": True, "item_closing_action": "sold"}],
    )
    assert len(remerciements(db)) == 1


def test_pas_de_remerciement_pour_une_vente_ancienne_ou_module_coupe(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str]
) -> None:
    compte, jeton = lucas
    vendu(db, compte, il_y_a=timedelta(days=5))
    dressing(client, jeton, [])
    assert not remerciements(db)
    vendu(db, compte, nom="Autre")
    client.put(f"/api/automatisation/comptes/{compte.id}/reglages", json={"modules": {"apres_vente": False}})
    dressing(client, jeton, [])
    assert not remerciements(db)


def test_conversation_introuvable_sans_alerte(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    monkeypatch: pytest.MonkeyPatch,
    telegram_faux: FauxTelegram,
) -> None:
    compte, jeton = lucas
    vendu(db, compte)
    dressing(client, jeton, [])
    a_heure(monkeypatch, 14, 15)
    t = client.get("/api/extension/taches/suivante", headers=entetes(jeton)).json()
    corps = {
        "ok": False,
        "erreur": "Conversation de l'acheteur introuvable dans la messagerie.",
        "erreur_vinted": False,
    }
    client.post(f"/api/extension/taches/{t['id']}/resultat", json=corps, headers=entetes(jeton))
    assert not telegram_faux.messages
    journal = db.scalars(select(JournalVinted).where(JournalVinted.type == "apres_vente")).all()
    assert any("non envoyé" in j.message for j in journal)


# --- Récapitulatif de 17 h 30 ----------------------------------------------------------------------


def test_recapitulatif_avec_le_pdf_des_bordereaux(
    db: Session, lucas: tuple[CompteVinted, str], monkeypatch: pytest.MonkeyPatch, telegram_faux: FauxTelegram
) -> None:
    compte, _ = lucas
    limite = horaires.maintenant() + timedelta(days=2)
    vendu(
        db,
        compte,
        fichier_bordereau=storage.ecrire_fichier("bordereaux", "b.pdf", pdf()),
        date_limite_envoi=limite,
    )
    vendu(db, None, nom="Jean ancien (Excel)", date_limite_envoi=horaires.maintenant() - timedelta(days=1))
    a_heure(monkeypatch, 17, 29)
    assert apres_vente.recapitulatif(db) == 0
    a_heure(monkeypatch, 17, 30)
    assert apres_vente.recapitulatif(db) == 1
    texte = telegram_faux.textes("1001")[-1]
    assert texte.startswith("📦 2 colis à préparer :") and "Jean ancien (Excel) ⚠️ en retard" in texte
    assert f"(avant le {horaires.local(limite):%d/%m})" in texte
    assert telegram_faux.documents[0]["nom"] == f"bordereaux-{horaires.local():%Y%m%d}.pdf"
    a_heure(monkeypatch, 18)
    assert apres_vente.recapitulatif(db) == 0  # une fois par jour


def test_rien_a_preparer_pas_de_message(
    db: Session, lucas: tuple[CompteVinted, str], monkeypatch: pytest.MonkeyPatch, telegram_faux: FauxTelegram
) -> None:
    a_heure(monkeypatch, 17, 45)
    assert apres_vente.recapitulatif(db) == 0
    assert not telegram_faux.messages


def test_sans_telegram_recapitulatif_en_push(db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    envois: list[tuple[str, str]] = []
    monkeypatch.setattr(
        push, "envoyer", lambda db, t, titre, corps="", url="/", forcer=False: envois.append((t, titre)) or 1
    )
    a_heure(monkeypatch, 17, 31)
    from app.api.deps import get_parametres

    get_parametres(db)
    vendu(db, None)
    apres_vente.recapitulatif(db)
    apres_vente.recapitulatif(db)
    assert envois == [("rappel_envois", "📦 1 colis à envoyer")]


# --- Rappel avant la date limite ---------------------------------------------------------------------


def test_rappel_la_veille_de_la_date_limite(
    db: Session, lucas: tuple[CompteVinted, str], telegram_faux: FauxTelegram
) -> None:
    compte, _ = lucas
    vendu(db, compte, nom="Bientôt", date_limite_envoi=horaires.maintenant() + timedelta(hours=20))
    vendu(db, compte, nom="Plus tard", date_limite_envoi=horaires.maintenant() + timedelta(hours=30))
    assert apres_vente.rappels_limite(db) == 1
    assert apres_vente.rappels_limite(db) == 0
    assert (
        telegram_faux.textes("1001")[-1].startswith("⏰ À déposer avant le")
        and "Bientôt" in telegram_faux.textes()[-1]
    )
    envoi = db.scalars(select(Envoi).where(Envoi.rappel_limite_le.is_not(None))).one()
    assert envoi.statut == StatutEnvoi.A_IMPRIMER
