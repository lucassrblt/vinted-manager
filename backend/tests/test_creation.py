"""Création d'annonce depuis les photos, provenance (stock, batch, pièce perso)."""

from decimal import Decimal as D
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Article, Batch, Envoi, PhotoArticle, Vente
from app.services import ia
from app.services.email_parser import lire_mail
from app.services.traitement import enregistrer_mail
from tests import test_mails_reels as reel
from tests.test_annonces import FauxClient
from tests.test_photos import jpeg

ANALYSE = {
    "types": ["etiquette", "devant", "dos", "defaut", "devant"],
    "marque": "Polo Ralph Lauren",
    "modele": None,
    "categorie": "Sweat demi-zip",
    "taille": "M",
    "couleur": "bleu marine",
    "etat": "bon_etat",
    "matiere": "100 % coton",
    "defauts": "petit trou au niveau de la manche",
    "titre": "Sweat demi-zip Polo Ralph Lauren bleu marine taille M",
    "description": "Sweat demi-zip Polo Ralph Lauren bleu marine, taille M.\nPorté mais en bon état, petit trou au niveau de la manche.",
    "mots_cles": ["#ralph lauren", "sweat"],
    "prix_estime": 38.4,
}


def _deposer(client: TestClient, n: int = 5) -> Any:
    fichiers = [("photos", (f"p{i}.jpg", jpeg(600, 800), "image/jpeg")) for i in range(n)]
    return client.post("/api/annonces/nouvelle", files=fichiers)


def test_analyse_des_photos_remplit_tout(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    faux = FauxClient(ANALYSE)
    monkeypatch.setattr(ia, "_client", lambda: faux)
    r = _deposer(client)
    assert r.status_code == 201, r.text
    assert r.json()["erreur_ia"] is None and r.json()["retouche_lancee"] is False  # pas de token en test
    a = db.get(Article, r.json()["article_id"])
    assert a is not None and a.statut == "recu_a_publier"
    assert (a.marque, a.taille, a.etat, a.defauts) == (
        "Polo Ralph Lauren",
        "M",
        "bon_etat",
        ANALYSE["defauts"],
    )
    assert a.titre_annonce == ANALYSE["titre"] and a.nom == ANALYSE["titre"]
    assert a.mots_cles_annonce == "ralph lauren, sweat" and a.prix_vente_cible == D("38")
    types = [p.type for p in db.scalars(select(PhotoArticle).order_by(PhotoArticle.ordre))]
    assert types == ["etiquette", "devant", "dos", "defaut", "detail"]  # un seul « devant »
    defaut = db.scalar(select(PhotoArticle).where(PhotoArticle.type == "defaut"))
    assert defaut is not None and defaut.statut == "original"  # jamais retouchée
    # Une seule requête, avec les 5 photos réduites et le style du vendeur
    appel = faux.appels[0]
    blocs = appel["messages"][0]["content"]
    assert sum(b["type"] == "image" for b in blocs) == 5
    assert "Porté mais en très bon état" in appel["system"]


def test_analyse_en_echec_cree_quand_meme_l_article(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ia, "_client", lambda: FauxClient(ia.ErreurIA("panne")))

    def echec(*_: Any) -> Any:
        raise ia.ErreurIA("Le service d'IA est momentanément indisponible.")

    monkeypatch.setattr(ia, "analyser_photos", echec)
    r = _deposer(client, 2)
    assert r.status_code == 201 and "indisponible" in r.json()["erreur_ia"]
    assert db.scalar(select(Article)) is not None


def test_trop_de_photos(client: TestClient) -> None:
    assert _deposer(client, 13).status_code == 422


def test_provenance_stock_fusionne(client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ia_factice", True)  # Sweat demi-zip Ralph Lauren bleu marine M
    batch = Batch(nom="Batch 3")
    db.add(batch)
    db.flush()
    stock = Article(
        nom="Pull demi-zip Ralph Lauren - bleu marine",
        marque="Ralph Lauren",
        taille="M",
        statut="commande",
        batch_id=batch.id,
        prix_achat_net=D("16.67"),
    )
    autre_marque = Article(
        nom="Polaire Patagonia - bleu", marque="Patagonia", taille="M", statut="recu_a_publier"
    )
    autre_taille = Article(
        nom="Pull demi-zip Ralph Lauren - bleu", marque="Ralph Lauren", taille="L", statut="recu_a_publier"
    )
    db.add_all([stock, autre_marque, autre_taille])
    db.commit()
    nouveau = _deposer(client, 3).json()["article_id"]
    suggestions = client.get(f"/api/annonces/{nouveau}/correspondances").json()
    assert [s["id"] for s in suggestions] == [stock.id] and suggestions[0]["batch_nom"] == "Batch 3"
    r = client.post(
        f"/api/annonces/{nouveau}/provenance", json={"mode": "stock", "article_stock_id": stock.id}
    )
    assert r.status_code == 200 and r.json()["article_id"] == stock.id
    db.expire_all()
    assert db.get(Article, nouveau) is None
    stock = db.get(Article, stock.id)
    assert stock is not None and stock.statut == "recu_a_publier" and stock.prix_achat_net == D("16.67")
    assert stock.titre_annonce and stock.couleur == "bleu marine" and stock.batch_id == batch.id
    assert len(db.scalars(select(PhotoArticle).where(PhotoArticle.article_id == stock.id)).all()) == 3


def test_provenance_perso_et_batch(client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ia_factice", True)
    nouveau = _deposer(client, 2).json()["article_id"]
    assert client.post(f"/api/annonces/{nouveau}/provenance", json={"mode": "perso"}).status_code == 200
    a = client.get(f"/api/articles/{nouveau}").json()
    assert a["perso"] is True and a["prix_achat_net"] == "0.00" and a["batch_id"] is None
    batch = Batch(nom="Batch 4")
    db.add(batch)
    db.commit()
    r = client.post(
        f"/api/annonces/{nouveau}/provenance",
        json={"mode": "batch", "batch_id": batch.id, "prix_achat": "12.5"},
    )
    assert r.status_code == 200
    a = client.get(f"/api/articles/{nouveau}").json()
    assert a["perso"] is False and a["batch_id"] == batch.id and a["prix_achat_net"] == "12.50"


def test_regenerer_seulement_la_description(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    a = Article(nom="Sweat", marque="H&M", statut="recu_a_publier", titre_annonce="Mon titre à garder")
    db.add(a)
    db.commit()
    faux = FauxClient({"titre": "Autre titre", "description": "Sweat H&M gris.", "mots_cles": []})
    monkeypatch.setattr(ia, "_client", lambda: faux)
    r = client.post(f"/api/annonces/{a.id}/generer", json={"cible": "description", "consigne": "plus court"})
    assert r.status_code == 200, r.text
    assert r.json()["titre"] == "Mon titre à garder" and r.json()["description"] == "Sweat H&M gris."
    assert "Consigne : plus court" in faux.appels[0]["messages"][0]["content"]


def test_vente_d_une_piece_perso_depuis_le_mail(client: TestClient, db: Session, regles: None) -> None:
    titre = "Sweat uniqlo gris"
    for brut in (reel.vente(titre, prix="5,00"), reel.bordereau(titre), reel.recue(titre)):
        enregistrer_mail(db, lire_mail(brut))
    [a_confirmer] = client.get("/api/ventes/a-confirmer").json()
    r = client.post("/api/ventes/piece-perso", json={"email_id": a_confirmer["email_id"]})
    assert r.status_code == 200, r.text
    article = db.get(Article, r.json()["article_id"])
    assert article is not None and article.perso and article.prix_achat_net == D("0")
    assert article.statut == "livre" and article.prix_vente_reel == D("5.00")
    envoi = db.scalar(select(Envoi))
    assert envoi is not None and envoi.statut == "livre"
    assert db.scalar(select(Vente)) is not None and client.get("/api/ventes/a-confirmer").json() == []
