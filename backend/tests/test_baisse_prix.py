"""Phase 6 : baisse de prix automatique (−5 % une seule fois, 48 à 72 h après la publication)."""

from datetime import timedelta
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, CompteVinted, TacheVinted
from app.models.enums import StatutArticle
from app.services import baisse_prix, horaires, reglages, telegram
from tests.outils_extension import LUCAS_VINTED, FauxTelegram, a_heure, creer_compte, entetes


@pytest.fixture
def lucas(db: Session, monkeypatch: pytest.MonkeyPatch) -> tuple[CompteVinted, str]:
    a_heure(monkeypatch, 14)
    compte, jeton = creer_compte(db, "Lucas", LUCAS_VINTED)
    compte.telegram_chat_id = "1001"
    db.commit()
    return compte, jeton


@pytest.fixture
def telegram_faux(monkeypatch: pytest.MonkeyPatch) -> FauxTelegram:
    faux = FauxTelegram()
    monkeypatch.setattr(telegram, "fabrique", lambda: faux)
    return faux


def article(db: Session, compte: CompteVinted, heures: float, **modifs: object) -> Article:
    a = Article(
        nom="Sweat Ralph Lauren",
        statut=StatutArticle.EN_LIGNE,
        compte_id=compte.id,
        prix_vente_cible=D("30"),
        prix_initial=D("30"),
        vinted_item_id=1000 + int(heures * 10),
        ai_photo_declare=True,
        date_publication=horaires.maintenant() - timedelta(hours=heures),
    )
    for k, v in modifs.items():
        setattr(a, k, v)
    db.add(a)
    db.commit()
    return a


def baisses(db: Session) -> list[TacheVinted]:
    return list(
        db.scalars(select(TacheVinted).where(TacheVinted.type == "modifier_prix").order_by(TacheVinted.id))
    )


def test_echeance_entre_48_et_72_h() -> None:
    r = reglages.DEFAUTS["prix"]
    for i in range(50):
        assert timedelta(hours=48) <= baisse_prix.echeance(Article(id=i), r) <= timedelta(hours=72)


def test_baisse_programmee_une_seule_fois(db: Session, lucas: tuple[CompteVinted, str]) -> None:
    a = article(db, lucas[0], 73)
    assert baisse_prix.planifier(db) == 1
    t = baisses(db)[0]
    assert (t.priorite, t.cle) == (5, f"baisse:{a.id}")
    # 30 € − 5 % = 28,50 €, au-dessus du plancher (82 % de 30 € = 24,60 → 25 €).
    assert t.payload == {
        "item_id": a.vinted_item_id,
        "prix_actuel": "30",
        "nouveau_prix": "28.5",
        "ai_photo": True,
        "article": a.nom,
    }
    t.statut = "faite"
    db.commit()
    assert baisse_prix.planifier(db) == 0


def test_pas_trop_tot_ni_trop_tard(db: Session, lucas: tuple[CompteVinted, str]) -> None:
    article(db, lucas[0], 40)  # trop tôt
    article(db, lucas[0], 24 * 10)  # publié il y a 10 jours : hors de la fenêtre, pas de baisse tardive
    assert baisse_prix.planifier(db) == 0


def test_jamais_apres_une_republication_ni_pour_une_annonce_importee(
    db: Session, lucas: tuple[CompteVinted, str]
) -> None:
    article(
        db,
        lucas[0],
        73,
        republications=1,
        derniere_publication_le=horaires.maintenant() - timedelta(hours=73),
    )
    article(db, lucas[0], 74, importe_vinted=True)
    assert baisse_prix.planifier(db) == 0


def test_jamais_sous_le_plancher(db: Session, lucas: tuple[CompteVinted, str]) -> None:
    a = article(db, lucas[0], 73, prix_vente_cible=D("25"))  # déjà au plancher (25 €)
    b = article(db, lucas[0], 74, prix_vente_cible=D("26"))  # 24,70 → 25 € (plancher)
    assert baisse_prix.planifier(db) == 1
    assert baisses(db)[0].payload["nouveau_prix"] == "25" and baisses(db)[0].article_id == b.id
    db.refresh(a)
    assert a.baisse_prix_le is not None  # vérifié une fois, pas de nouvel essai


def test_module_coupe(client: TestClient, db: Session, lucas: tuple[CompteVinted, str]) -> None:
    article(db, lucas[0], 73)
    client.put(f"/api/automatisation/comptes/{lucas[0].id}/reglages", json={"modules": {"prix": False}})
    db.expire_all()
    assert baisse_prix.planifier(db) == 0


def test_resultat(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    monkeypatch: pytest.MonkeyPatch,
    telegram_faux: FauxTelegram,
) -> None:
    compte, jeton = lucas
    a = article(db, compte, 73)
    b = article(db, compte, 74, nom="Pull")
    baisse_prix.planifier(db)
    for i, corps in enumerate(
        (
            {"ok": True, "resultat": {"item_id": 1, "prix": "28.5"}},
            {
                "ok": False,
                "erreur": "Champ manquant dans l'annonce lue : item_attributes.",
                "erreur_vinted": False,
            },
        )
    ):
        a_heure(monkeypatch, 15, i * 2)
        t = client.get("/api/extension/taches/suivante", headers=entetes(jeton)).json()
        client.post(f"/api/extension/taches/{t['id']}/resultat", json=corps, headers=entetes(jeton))
    db.expire_all()
    faite = next(t for t in baisses(db) if t.statut == "faite")  # l'ordre dépend des délais tirés au hasard
    baissee = db.get(Article, faite.article_id)
    assert (
        baissee is not None
        and baissee.prix_vente_cible == D("28.50")
        and baissee.prix_avant_baisse == D("30.00")
    )
    autre = a if baissee.id == b.id else b
    assert db.get(Article, autre.id).prix_vente_cible == D("30.00")  # type: ignore[union-attr]
    # Champ manquant : le module est coupé (les suivantes échoueraient pareil) et Lucas est prévenu.
    assert reglages.module_actif(db.get(CompteVinted, compte.id), "prix") is False  # type: ignore[arg-type]
    assert "Baisse de prix automatique coupée" in telegram_faux.textes()[-1]
