from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, HistoriqueStatut

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


def _article(client: TestClient, **kw: object) -> dict:
    corps = {"nom": "Hoodie Carhartt WIP - noir", "taille": "M", "prix_achat_brut": "20.25"} | kw
    r = client.post("/api/articles", json=corps)
    assert r.status_code == 201, r.text
    return r.json()


def test_creation_et_calculs(client: TestClient) -> None:
    a = _article(client, prix_vente_cible="38", marque="Carhartt WIP")
    assert a["prix_achat_net"] == "20.25"
    assert a["statut"] == "recu_a_publier"
    assert D(a["marge"]) == D("17.75")
    assert a["indicateur"] == "Sous l'objectif"


def test_edition_inline_recalcule_le_net(client: TestClient) -> None:
    a = _article(client)
    r = client.patch(f"/api/articles/{a['id']}", json={"remise": "1.25"})
    assert r.json()["prix_achat_net"] == "19.00"
    r = client.patch(f"/api/articles/{a['id']}", json={"taille": "L"})
    assert r.json()["taille"] == "L" and r.json()["prix_achat_net"] == "19.00"


def test_changement_statut_horodate(client: TestClient, db: Session) -> None:
    a = _article(client)
    client.post(f"/api/articles/{a['id']}/statut", json={"statut": "en_ligne"})
    r = client.post(f"/api/articles/{a['id']}/statut", json={"statut": "vendu"})
    assert r.json()["date_publication"] and r.json()["date_vente"]
    timeline = client.get(f"/api/articles/{a['id']}/timeline").json()
    assert [t["nouveau_statut"] for t in timeline] == ["recu_a_publier", "en_ligne", "vendu"]
    assert timeline[2]["ancien_statut"] == "en_ligne"


def test_liste_filtres_tri_pagination(client: TestClient) -> None:
    for i in range(5):
        _article(client, nom=f"Pull Ralph Lauren {i}", marque="Ralph Lauren", prix_vente_cible=str(30 + i))
    _article(client, nom="Bonnet Ralph Lauren", marque="Ralph Lauren", taille="TU")
    _article(client, nom="T-shirt CDG", marque="Comme des Garçons Play")
    r = client.get(
        "/api/articles",
        params={"marque": "Ralph Lauren", "taille_page": 2, "tri": "prix_vente", "ordre": "desc"},
    )
    page = r.json()
    assert page["total"] == 6 and len(page["items"]) == 2
    assert page["items"][0]["prix_vente"] == "34.00"
    assert client.get("/api/articles", params={"q": "bonnet"}).json()["total"] == 1
    assert client.get("/api/articles", params={"taille": "TU"}).json()["total"] == 1
    filtres = client.get("/api/articles/filtres").json()
    assert filtres["marques"] == ["Comme des Garçons Play", "Ralph Lauren"]


def test_actions_groupees(client: TestClient, db: Session) -> None:
    ids = [_article(client)["id"] for _ in range(3)]
    r = client.post("/api/articles/bulk", json={"ids": ids[:2], "action": "publie_aujourdhui"})
    assert r.json() == {"modifies": 2}
    publies = db.scalars(select(Article).where(Article.statut == "en_ligne")).all()
    assert len(publies) == 2 and all(a.date_publication for a in publies)

    b = client.post("/api/batches", json={"nom": "Batch test"}).json()
    client.post("/api/articles/bulk", json={"ids": ids, "action": "batch", "batch_id": b["id"]})
    assert client.get("/api/articles", params={"batch_id": b["id"]}).json()["total"] == 3

    client.post("/api/articles/bulk", json={"ids": [ids[2]], "action": "supprimer"})
    assert db.get(Article, ids[2]) is None


def test_batch_avec_repartition_remise(client: TestClient, db: Session) -> None:
    r = client.post(
        "/api/batches",
        json={
            "nom": "Batch 5",
            "fournisseur": "Hacoo",
            "date_commande": "2026-10-20",
            "remise_globale": "10.56",
            "articles": [
                {
                    "nom": "Pull demi-zip Ralph Lauren - noir",
                    "taille": "M",
                    "prix_achat_brut": "17.64",
                    "quantite": 8,
                },
                {"nom": "T-shirt CDG Play - noir", "taille": "M", "prix_achat_brut": "7.85", "quantite": 4},
                {
                    "nom": "Bonnet Ralph Lauren - noir",
                    "taille": "TU",
                    "prix_achat_brut": "4.98",
                    "quantite": 4,
                },
            ],
        },
    )
    assert r.status_code == 201, r.text
    batch = r.json()
    assert batch["nb_articles"] == 16
    articles = db.scalars(select(Article).where(Article.batch_id == batch["id"])).all()
    assert sum(a.remise for a in articles) == D("10.56")
    assert all(a.prix_achat_net == a.prix_achat_brut - a.remise for a in articles)
    assert all(a.statut == "commande" for a in articles)
    assert D(batch["total_paye"]) == D("192.44") - D("10.56")
    # Nom unique
    assert client.post("/api/batches", json={"nom": "Batch 5"}).status_code == 409


def test_stats_batch_et_delai(client: TestClient, db: Session) -> None:
    b = client.post("/api/batches", json={"nom": "B"}).json()
    a1 = _article(client, batch_id=b["id"], prix_achat_brut="10")
    _article(client, batch_id=b["id"], prix_achat_brut="10")
    art = db.get(Article, a1["id"])
    assert art is not None
    art.statut = "vendu"
    art.prix_vente_reel = D("30")
    art.date_publication = datetime(2026, 10, 1, 10, tzinfo=UTC)
    art.date_vente = datetime(2026, 10, 2, 10, tzinfo=UTC)
    db.commit()
    s = client.get(f"/api/batches/{b['id']}").json()["batch"]
    assert (s["nb_articles"], s["nb_publies"], s["nb_vendus"]) == (2, 1, 1)
    assert D(s["ca"]) == D("30") and D(s["marge_realisee"]) == D("20") and D(s["coefficient_ventes"]) == 3
    assert s["delai_moyen_heures"] == 24
    assert D(s["valeur_stock_restant"]) == D("10")


def test_preuves_upload_validation_et_zip(client: TestClient) -> None:
    a = _article(client)
    r = client.post(
        "/api/preuves",
        data={"article_id": str(a["id"]), "type": "facture"},
        files={"fichier": ("facture hacoo.pdf", PDF, "application/pdf")},
    )
    assert r.status_code == 201, r.text
    preuve = r.json()
    f = client.get(f"/api/preuves/{preuve['id']}/fichier")
    assert f.status_code == 200 and f.content == PDF

    # Faux PDF, type interdit
    r = client.post(
        "/api/preuves",
        data={"article_id": str(a["id"])},
        files={"fichier": ("x.pdf", b"MZ\x90\x00", "application/pdf")},
    )
    assert r.status_code == 415
    r = client.post(
        "/api/preuves",
        data={"article_id": str(a["id"])},
        files={"fichier": ("x.exe", b"MZ", "application/x-msdownload")},
    )
    assert r.status_code == 415

    z = client.get(f"/api/articles/{a['id']}/preuves.zip")
    assert z.status_code == 200 and z.content[:2] == b"PK"
    assert client.delete(f"/api/preuves/{preuve['id']}").status_code == 204


def test_preuve_trop_grosse(client: TestClient) -> None:
    from app.config import get_settings

    a = _article(client)
    get_settings().max_upload_mb = 1
    try:
        r = client.post(
            "/api/preuves",
            data={"article_id": str(a["id"])},
            files={"fichier": ("gros.pdf", b"%PDF" + b"0" * (1024 * 1024 + 10), "application/pdf")},
        )
        assert r.status_code == 413
    finally:
        get_settings().max_upload_mb = 15


def test_compta_periode_et_urssaf(client: TestClient, db: Session) -> None:
    for prix, quand in (
        ("30", datetime(2026, 9, 30, 23, 30, tzinfo=UTC)),
        ("45", datetime(2026, 10, 5, 12, tzinfo=UTC)),
    ):
        a = _article(client, prix_achat_brut="15")
        art = db.get(Article, a["id"])
        assert art is not None
        art.statut, art.prix_vente_reel, art.date_vente = "vendu", D(prix), quand
    db.commit()
    # 30/09 23h30 UTC = 01/10 01h30 à Paris : la vente compte en octobre
    k = client.get("/api/compta/kpis", params={"du": "2026-10-01", "au": "2026-10-31"}).json()
    assert D(k["ca_encaisse"]) == D("75") and k["nb_ventes"] == 2
    assert D(k["cotisations_estimees"]) == D("9.23")  # 75 × 12,3 %
    assert D(k["marge_realisee"]) == D("45")

    csv = client.get("/api/compta/urssaf.csv", params={"mois": "2026-10"}).text
    assert "01/10/2026" in csv and "75,00" in csv and "Total du mois" in csv
    assert client.get("/api/compta/urssaf.csv", params={"mois": "2026-13"}).status_code == 422

    series = client.get("/api/compta/series", params={"granularite": "mois"}).json()
    assert [(s["periode"], s["nb_ventes"]) for s in series] == [("2026-10", 2)]


def test_ecran_du_jour_articles_lents(client: TestClient, db: Session) -> None:
    a = _article(client)
    art = db.get(Article, a["id"])
    assert art is not None
    art.statut = "en_ligne"
    art.date_publication = datetime.now(UTC) - timedelta(days=9)
    db.commit()
    d = client.get("/api/dashboard/jour").json()
    assert [x["id"] for x in d["articles_lents"]] == [a["id"]]
    assert d["objectif_jour"]["objectif"] == 3


def test_sourcing_perf_historique(client: TestClient, db: Session) -> None:
    a = _article(
        client, nom="Pull Ralph Lauren - noir", marque="Ralph Lauren", categorie="Pull", prix_achat_brut="20"
    )
    art = db.get(Article, a["id"])
    assert art is not None
    art.statut, art.prix_vente_reel = "vendu", D("50")
    db.commit()
    p = client.post(
        "/api/sourcing", json={"marque": "Ralph Lauren", "produit": "Cable-Knit", "categorie": "Pull torsadé"}
    )
    piste = p.json()
    assert piste["perf_nb_ventes"] == 1 and piste["perf_base"] == "marque+categorie"
    assert D(piste["perf_coefficient_moyen"]) == D("2.50")


def test_suppression_article_cascade(client: TestClient, db: Session) -> None:
    a = _article(client)
    assert client.delete(f"/api/articles/{a['id']}").status_code == 204
    assert db.scalars(select(HistoriqueStatut)).all() == []
    assert client.get(f"/api/articles/{a['id']}").status_code == 404
