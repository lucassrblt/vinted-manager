"""Phase 5 : republication différenciée (photos transformées, texte vérifié, nouvelle annonce)."""

import io
import random
from datetime import timedelta
from decimal import Decimal as D
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Article,
    CompteVinted,
    ConversationVinted,
    FavoriVinted,
    JournalVinted,
    PhotoArticle,
    TacheVinted,
)
from app.models.enums import StatutArticle
from app.services import couleur, horaires, ia, reglages, republication, storage, telegram
from tests.outils_extension import (
    LUCAS_VINTED,
    FauxTelegram,
    a_heure,
    article_pret,
    creer_compte,
    entetes,
    jpeg,
)

R = reglages.DEFAUTS["republication"]


@pytest.fixture
def lucas(db: Session) -> tuple[CompteVinted, str]:
    compte, jeton = creer_compte(db, "Lucas", LUCAS_VINTED)
    compte.telegram_chat_id = "1001"
    db.commit()
    return compte, jeton


@pytest.fixture
def telegram_faux(monkeypatch: pytest.MonkeyPatch) -> FauxTelegram:
    faux = FauxTelegram()
    monkeypatch.setattr(telegram, "fabrique", lambda: faux)
    return faux


@pytest.fixture
def reecriture(monkeypatch: pytest.MonkeyPatch) -> list[ia.Reecriture]:
    reponses = [
        ia.Reecriture(
            titre="T-shirt ACG Nike violet lavande taille M",
            description="T-shirt violet de la marque Nike ACG en coton, taille M, super sympa.\nNeuf avec étiquette.",
        )
    ]
    monkeypatch.setattr(
        ia, "reecrire_annonce", lambda *a, **k: reponses.pop(0) if len(reponses) > 1 else reponses[0]
    )
    return reponses


@pytest.fixture
def en_ligne(db: Session, lucas: tuple[CompteVinted, str], monkeypatch: pytest.MonkeyPatch) -> Article:
    """T-shirt complet, publié il y a 6 jours."""
    a_heure(monkeypatch, 14)
    a = article_pret(db, lucas[0])
    a.statut = StatutArticle.EN_LIGNE
    a.vinted_item_id = 10495425715
    a.ai_photo_declare = True
    a.date_publication = horaires.maintenant() - timedelta(days=6)
    a.prix_initial = D("24")
    db.commit()
    return a


def taches_de(db: Session, type_tache: str | None = None) -> list[TacheVinted]:
    q = select(TacheVinted).order_by(TacheVinted.id)
    if type_tache:
        q = q.where(TacheVinted.type == type_tache)
    return list(db.scalars(q))


# --- Transformations ---------------------------------------------------------------------------


def test_zoom_masque_les_coins_de_la_rotation() -> None:
    assert republication.zoom_necessaire(600, 800, 2.5) == pytest.approx(0.054, abs=0.002)
    assert republication.zoom_necessaire(600, 800, 1.5) < republication.zoom_necessaire(600, 800, 2.5)


def test_transformation_dans_les_plages_sans_coin_vide_ni_metadonnees() -> None:
    gris = jpeg(600, 800, (128, 128, 128))
    for graine in range(10):
        sens = 1 if graine % 2 else -1
        sortie, t = republication.transformer(gris, random.Random(graine), sens, R)
        image = Image.open(io.BytesIO(sortie))
        assert image.size == (600, 800) and not image.getexif()
        assert 1.5 <= abs(t["angle"]) <= 2.5 and (t["angle"] > 0) == (sens > 0)
        assert 4.5 <= t["zoom"] <= 5.6 and 2 <= t["luminosite"] <= 5 and 85 <= t["qualite"] <= 92
        for coin in ((0, 0), (599, 0), (0, 799), (599, 799)):
            assert min(image.getpixel(coin)) > 100  # type: ignore[arg-type]  # pas de coin noir
        assert sortie != gris


def test_premiere_photo_reste_fidele() -> None:
    for teinte in ((128, 128, 128), (40, 60, 160), (230, 200, 80)):
        source = jpeg(600, 800, teinte)
        sortie, _ = republication.transformer(source, random.Random(1), 1, R, premiere=True)
        assert couleur.ecart(source, sortie) <= republication.DELTA_E_MAX_PREMIERE


# --- Texte -------------------------------------------------------------------------------------


def test_verification_des_informations_obligatoires() -> None:
    a = Article(
        nom="x", marque="Polo Ralph Lauren", taille="M", etat="bon_etat", defauts="petite tache sur la manche",
        matiere="100% coton", mots_cles_annonce="ralph lauren, sweat",
    )  # fmt: skip
    bon = (
        "Sweat Polo Ralph Lauren taille M",
        "En coton. Porté mais en bon état, petite tache sur la manche.",
    )
    assert republication.manquants(a, *bon) == []
    assert republication.manquants(a, "Sweat Ralph Lauren", "En coton, très joli.") == [
        "marque", "taille", "état", "défauts",
    ]  # fmt: skip


def test_texte_refuse_deux_fois_garde_l_annonce_actuelle(
    db: Session, lucas: tuple[CompteVinted, str], en_ligne: Article, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        ia, "reecrire_annonce", lambda *a, **k: ia.Reecriture(titre="T-shirt violet", description="Joli.")
    )
    titre, description = republication.texte_republication(db, lucas[0], en_ligne)
    assert (titre, description) == (en_ligne.titre_annonce, en_ligne.description_annonce)
    refus = db.scalars(select(JournalVinted).where(JournalVinted.type == "republication")).all()
    assert len(refus) == 2 and "marque" in refus[0].message


# --- Planification ---------------------------------------------------------------------------------


def test_republication_programmee_tous_les_5_jours(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str], en_ligne: Article, reecriture: Any
) -> None:
    assert republication.planifier(db) == 1
    t = taches_de(db, "republication")[0]
    assert t.priorite == 5 and timedelta(0) <= t.executer_apres - horaires.maintenant() <= timedelta(
        minutes=20
    )
    p = t.payload
    assert p["ancien_item_id"] == 10495425715 and p["titre"] == "T-shirt ACG Nike violet lavande taille M"
    assert (p["prix"], p["condition_id"], p["package_size_id"], p["ai_photo"]) == ("24", 6, 1, True)
    assert [x["index"] for x in p["photos"]] == [0, 1, 2, 3, 4]
    assert len(p["transformations"]) == 5
    assert republication.planifier(db) == 0  # une seule à la fois par compte
    # Photo servie à l'extension, seulement pour ce compte.
    r = client.get(f"/api/extension/taches/{t.id}/photos/0", headers=entetes(lucas[1]))
    assert r.status_code == 200 and r.headers["content-type"] == "image/jpeg"
    _, autre = creer_compte(db, "Sœur", 3209999999)
    assert client.get(f"/api/extension/taches/{t.id}/photos/0", headers=entetes(autre)).status_code == 404


def test_pas_avant_5_jours_ni_la_nuit(
    db: Session,
    lucas: tuple[CompteVinted, str],
    en_ligne: Article,
    monkeypatch: pytest.MonkeyPatch,
    reecriture: Any,
) -> None:
    en_ligne.date_publication = horaires.maintenant() - timedelta(days=4)
    db.commit()
    assert republication.planifier(db) == 0
    en_ligne.date_publication = horaires.maintenant() - timedelta(days=6)
    db.commit()
    a_heure(monkeypatch, 23, 30)
    assert republication.planifier(db) == 0


def test_reportee_si_conversation_recente(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    en_ligne: Article,
    monkeypatch: pytest.MonkeyPatch,
    reecriture: Any,
) -> None:
    conv = ConversationVinted(
        id="c1",
        compte_id=lucas[0].id,
        article_id=en_ligne.id,
        dernier_message_le=horaires.maintenant() - timedelta(minutes=20),
    )
    db.add(conv)
    db.commit()
    assert republication.planifier(db) == 0
    conv.dernier_message_le = horaires.maintenant() - timedelta(hours=2)
    db.commit()
    assert republication.planifier(db) == 1
    # Message arrivé entre-temps : la tâche est reportée de 30 min au moment de partir.
    a_heure(monkeypatch, 14, 25)
    conv.dernier_message_le = horaires.maintenant() - timedelta(minutes=5)
    db.commit()
    assert client.get("/api/extension/taches/suivante", headers=entetes(lucas[1])).status_code == 204
    db.expire_all()
    t = taches_de(db, "republication")[0]
    assert t.statut == "a_faire" and t.executer_apres > horaires.maintenant() + timedelta(minutes=25)


def test_offres_aux_favoris_avant_la_republication(
    db: Session, lucas: tuple[CompteVinted, str], en_ligne: Article, reecriture: Any
) -> None:
    compte = lucas[0]
    for membre, statut, offre in ((1, "ignore", False), (2, "relance", True), (3, "erreur", False)):
        db.add(
            FavoriVinted(
                compte_id=compte.id, vinted_item_id=en_ligne.vinted_item_id, membre_id=membre, recu_le=horaires.maintenant(),
                statut=statut, offre_envoyee=offre, article_id=en_ligne.id,
            )
        )  # fmt: skip
    db.commit()
    assert republication.planifier(db) == 0
    relances = taches_de(db, "relance_favori")
    assert sorted(t.payload["membre_id"] for t in relances) == [1]  # jamais après une relance en échec (3)
    assert all(t.payload["montant"] == "21.5" and t.payload["avant_republication"] for t in relances)
    assert not taches_de(db, "republication")
    for t in relances:  # relances faites
        t.statut = "faite"
    db.commit()
    assert republication.planifier(db) == 1


def test_annonce_importee_sans_photo_telecharge_ses_photos(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    reecriture: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a_heure(monkeypatch, 14)
    a = Article(
        nom="Sweat importé", titre_annonce="Sweat importé", description_annonce="Sweat gris, taille M.\nTrès bon état.",
        statut=StatutArticle.EN_LIGNE, compte_id=lucas[0].id, vinted_item_id=555, importe_vinted=True,
        prix_vente_cible=D("10"), etat="tres_bon_etat", taille="M",
        vinted_photos=["https://images1.vinted.net/a.jpg", "https://images1.vinted.net/b.jpg"],
        date_publication=horaires.maintenant() - timedelta(days=7),
    )  # fmt: skip
    db.add(a)
    db.commit()
    assert republication.planifier(db) == 0
    t = taches_de(db, "photos_reference")[0]
    assert t.payload == {"urls": a.vinted_photos}
    fichiers = [("fichiers", (f"{i}.jpg", jpeg(400, 500), "image/jpeg")) for i in range(2)]
    r = client.post(
        f"/api/extension/articles/{a.id}/photos-reference", files=fichiers, headers=entetes(lucas[1])
    )
    assert r.json() == {"photos": 2}
    types = [
        p.type
        for p in db.scalars(
            select(PhotoArticle).where(PhotoArticle.article_id == a.id).order_by(PhotoArticle.ordre)
        )
    ]
    assert types == ["devant", "detail"]
    assert (
        client.post(
            f"/api/extension/articles/{a.id}/photos-reference", files=fichiers, headers=entetes(lucas[1])
        ).status_code
        == 409
    )
    t.statut = "faite"
    db.commit()
    assert republication.planifier(db) == 1
    assert taches_de(db, "republication")[0].payload["ai_photo"] is True  # inconnu pour une annonce importée


# --- Résultat ----------------------------------------------------------------------------------------


def _executer(client: TestClient, jeton: str, corps: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> int:
    a_heure(monkeypatch, 15)
    t = client.get("/api/extension/taches/suivante", headers=entetes(jeton)).json()
    assert t["type"] == "republication"
    r = client.post(f"/api/extension/taches/{t['id']}/resultat", json=corps, headers=entetes(jeton))
    assert r.status_code == 204, r.text
    return int(t["id"])


def test_republication_reussie(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    en_ligne: Article,
    reecriture: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    republication.planifier(db)
    tid = _executer(client, lucas[1], {"ok": True, "resultat": {"nouvel_item_id": 10521949755}}, monkeypatch)
    db.expire_all()
    a = db.get(Article, en_ligne.id)
    assert a is not None and (a.vinted_item_id, a.republications) == (10521949755, 1)
    assert (
        a.derniere_publication_le == horaires.maintenant()
        and a.titre_annonce == "T-shirt ACG Nike violet lavande taille M"
    )
    assert not storage.chemin_absolu(f"republication/tache-{tid}").exists()  # fichiers temporaires supprimés
    # Prochaine republication dans 5 jours, rotation dans l'autre sens.
    assert republication.planifier(db) == 0


def test_ancienne_annonce_non_supprimee_alerte(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    en_ligne: Article,
    reecriture: Any,
    monkeypatch: pytest.MonkeyPatch,
    telegram_faux: FauxTelegram,
) -> None:
    republication.planifier(db)
    corps = {
        "ok": False,
        "erreur": "403 sur delete",
        "erreur_vinted": True,
        "resultat": {"nouvel_item_id": 777},
    }
    _executer(client, lucas[1], corps, monkeypatch)
    db.expire_all()
    assert db.get(Article, en_ligne.id).vinted_item_id == 777  # type: ignore[union-attr]
    assert "Ancienne annonce non supprimée" in telegram_faux.textes()[-1]


def test_echec_l_ancienne_reste_en_ligne(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    en_ligne: Article,
    reecriture: Any,
    monkeypatch: pytest.MonkeyPatch,
    telegram_faux: FauxTelegram,
) -> None:
    republication.planifier(db)
    _executer(
        client,
        lucas[1],
        {"ok": False, "erreur": "Annonce vendue entre-temps", "erreur_vinted": False},
        monkeypatch,
    )
    db.expire_all()
    a = db.get(Article, en_ligne.id)
    assert a is not None and a.vinted_item_id == 10495425715 and a.republication_bloquee
    assert "réautorise la republication" in telegram_faux.textes()[-1]
    # Jamais de nouvel essai automatique tant que Lucas n'a pas vérifié.
    a_heure(monkeypatch, 16)
    assert republication.planifier(db) == 0
    assert client.post(f"/api/articles/{a.id}/republication/debloquer").status_code == 204
    db.expire_all()
    assert republication.planifier(db) == 1
