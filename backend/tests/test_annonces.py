import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Article, Message, Parametres
from app.services import ia, offres, prix_conseille

PARAMS = Parametres(
    id=1, coefficient_min=D("2"), coefficient_max=D("4"), arrondi_seuil=D("30"), arrondi_pas=D("5")
)


def _vendu(
    nom: str, marque: str, categorie: str, prix: str, jours: float | None = None, achat: str = "15"
) -> Article:
    pub = datetime(2026, 10, 1, tzinfo=UTC)
    return Article(
        id=hash(nom + prix) % 100000,
        nom=nom,
        marque=marque,
        categorie=categorie,
        statut="vendu",
        prix_achat_net=D(achat),
        prix_vente_reel=D(prix),
        date_publication=pub if jours is not None else None,
        date_vente=pub + timedelta(days=jours) if jours is not None else None,
    )


# --- Prix conseillé ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("brut", "attendu"),
    [("24.4", "24"), ("24.5", "25"), ("29.9", "30"), ("32", "30"), ("43", "45"), ("47.4", "45")],
)
def test_arrondi(brut: str, attendu: str) -> None:
    assert prix_conseille.arrondir(D(brut), PARAMS) == D(attendu)


def test_prix_meme_marque_et_categorie() -> None:
    vendus = [
        _vendu("Pull RL noir", "Ralph Lauren", "Pull", p, j)
        for p, j in (("40", 1), ("45", 2), ("45", 3), ("52.3", 3.2), ("38", 2.3))
    ] + [_vendu("Pull Lacoste", "Lacoste", "Pull", "20", 1)]
    article = Article(
        id=1, nom="Pull RL gris", marque="Ralph Lauren", categorie="Pull", prix_achat_net=D("16.67")
    )
    r = prix_conseille.calculer(article, vendus, PARAMS)
    assert r.base == "marque+categorie" and r.nb_ventes == 5 and not r.estimation
    assert r.mediane == D("45.00") and r.prix == D("45")
    assert r.raisonnement.startswith(
        "5 ventes similaires (même marque et même catégorie), médiane 45 €, vendues en 2,3 jours"
    )
    assert "coefficient 2,7" in r.raisonnement


def test_prix_repli_sur_categorie_puis_marque() -> None:
    vendus = [_vendu(f"Pull {i}", "Autre", "Pull", "30") for i in range(3)]
    article = Article(id=1, nom="Pull RL", marque="Ralph Lauren", categorie="Pull", prix_achat_net=D("10"))
    assert prix_conseille.calculer(article, vendus, PARAMS).base == "categorie"
    vendus = [_vendu(f"Bonnet {i}", "Ralph Lauren", "Bonnet", "18") for i in range(3)]
    assert prix_conseille.calculer(article, vendus, PARAMS).base == "marque"


def test_prix_releve_si_sous_objectif() -> None:
    vendus = [_vendu(f"T {i}", "Carhartt WIP", "T-shirt", "12") for i in range(3)]
    article = Article(
        id=1, nom="T-shirt", marque="Carhartt WIP", categorie="T-shirt", prix_achat_net=D("8.74")
    )
    r = prix_conseille.calculer(article, vendus, PARAMS)
    assert r.sous_objectif_releve and r.prix == D("18")  # 8,74 × 2 = 17,48 -> 18 €
    assert "relevé" in r.raisonnement


def test_estimation_sans_historique() -> None:
    article = Article(id=1, nom="Veste", marque="Inconnue", categorie="Veste", prix_achat_net=D("20.97"))
    r = prix_conseille.calculer(article, [], PARAMS)
    assert r.estimation and r.prix == D("50")  # 20,97 × 2,5 = 52,4 -> 50 €
    assert r.raisonnement.startswith("Estimation")


def test_nouveau_prix_article_lent() -> None:
    a = Article(id=1, nom="Pull", prix_achat_net=D("16.67"), prix_vente_cible=D("45"), statut="en_ligne")
    r = prix_conseille.calculer(a, [], PARAMS)
    assert prix_conseille.nouveau_prix_article_lent(a, r, PARAMS) == D("40")
    # Jamais sous le plancher (coefficient minimal)
    b = Article(id=2, nom="Pull", prix_achat_net=D("16.67"), prix_vente_cible=D("35"), statut="en_ligne")
    assert prix_conseille.nouveau_prix_article_lent(b, prix_conseille.calculer(b, [], PARAMS), PARAMS) is None


# --- Offres -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("offre", "decision", "propose"),
    [
        ("42", "accepter", None),
        ("30", "contre_proposer", "38"),
        ("20", "refuser", None),
        ("34", "contre_proposer", "40"),
    ],
)
def test_analyse_offre(offre: str, decision: str, propose: str | None) -> None:
    a = Article(id=1, nom="Pull", prix_achat_net=D("16.67"), prix_vente_cible=D("45"))
    r = offres.analyser(a, D(offre), PARAMS)
    assert r.decision == decision
    assert r.montant_propose == (D(propose) if propose else None)
    assert r.prix_plancher == D("35")  # 16,67 × 2 = 33,34 -> 34 -> arrondi au multiple de 5 au-dessus
    assert r.marge_si_accepte == D(offre) - D("16.67")
    if r.montant_propose:
        assert r.montant_propose >= r.prix_plancher


# --- IA ---------------------------------------------------------------------------------------


class FauxClient:
    def __init__(self, sortie: Any, stop: str = "end_turn") -> None:
        self.sortie, self.stop, self.appels = sortie, stop, []
        self.messages = self

    def create(self, **kw: Any) -> Any:
        self.appels.append(kw)
        if isinstance(self.sortie, Exception):
            raise self.sortie
        return SimpleNamespace(
            stop_reason=self.stop,
            content=[SimpleNamespace(type="text", text=json.dumps(self.sortie))],
            usage=SimpleNamespace(input_tokens=10, output_tokens=20),
        )


def test_generation_annonce(monkeypatch: pytest.MonkeyPatch) -> None:
    faux = FauxClient({"titre": "Pull demi-zip Ralph Lauren gris clair M avec un titre beaucoup trop long",
                       "description": "Pull en très bon état. Possibilité de faire un lot.", "mots_cles": ["#Ralph Lauren", "pull"]})  # fmt: skip
    monkeypatch.setattr(ia, "_client", lambda: faux)
    annonce = ia.generer_annonce(
        {"marque": "Ralph Lauren", "categorie": "Pull", "etat": "Très bon état"}, None
    )
    assert len(annonce.titre) <= 60 and not annonce.titre.endswith(" ")
    assert annonce.mots_cles == ["ralph lauren", "pull"]
    appel = faux.appels[0]
    assert appel["model"] == get_settings().anthropic_model
    assert appel["output_config"]["format"]["type"] == "json_schema"
    assert "N'affirme jamais" in appel["system"]  # prompt chargé depuis app/prompts/
    assert "Porté mais en très bon état" in appel["system"]  # consignes de style incluses
    assert "Marque : Ralph Lauren" in appel["messages"][0]["content"]


def _erreur(
    classe: type[anthropic.APIStatusError], code: int, message: str = "x"
) -> anthropic.APIStatusError:
    reponse = httpx.Response(code, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))
    return classe(message, response=reponse, body=None)


@pytest.mark.parametrize(
    ("exc", "attendu"),
    [
        (_erreur(anthropic.AuthenticationError, 401), "Clé API Anthropic refusée"),
        (_erreur(anthropic.RateLimitError, 429), "limite de débit"),
        (
            _erreur(anthropic.BadRequestError, 400, "Your credit balance is too low"),
            "Crédit API Anthropic épuisé",
        ),
        (_erreur(anthropic.InternalServerError, 529), "indisponible ou surchargé"),
        (
            anthropic.APIConnectionError(request=httpx.Request("POST", "https://api.anthropic.com")),
            "Impossible de joindre",
        ),
    ],
)
def test_erreurs_ia_claires(monkeypatch: pytest.MonkeyPatch, exc: Exception, attendu: str) -> None:
    monkeypatch.setattr(ia, "_client", lambda: FauxClient(exc))
    with pytest.raises(ia.ErreurIA, match=attendu):
        ia.generer_annonce({"marque": "X"}, None)


def test_refus_et_cle_absente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ia, "_client", lambda: FauxClient({"reponse": "x"}, stop="refusal"))
    with pytest.raises(ia.ErreurIA, match="refusé"):
        ia.suggerer_reponse("Bonjour", "message", None, None, [])
    monkeypatch.undo()
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    with pytest.raises(ia.ErreurIA, match="ANTHROPIC_API_KEY"):
        ia.generer_annonce({"marque": "X"}, None)


# --- API --------------------------------------------------------------------------------------


@pytest.fixture
def factice(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "ia_factice", True)


def _article(db: Session, **kw: Any) -> Article:
    a = Article(**({"nom": "Pull demi-zip Ralph Lauren - Gris", "marque": "Ralph Lauren", "categorie": "Pull",
                    "taille": "M", "couleur": "Gris", "prix_achat_net": D("16.67"), "statut": "recu_a_publier"} | kw))  # fmt: skip
    db.add(a)
    db.commit()
    return a


def test_parcours_annonce(client: TestClient, db: Session, factice: None) -> None:
    a = _article(db)
    assert [x["id"] for x in client.get("/api/annonces/a-publier").json()] == [a.id]
    fiche = client.get(f"/api/annonces/{a.id}").json()
    assert fiche["prix_conseille"]["estimation"] is True and fiche["ia_disponible"] is True
    r = client.post(f"/api/annonces/{a.id}/generer", json={"marque": "Ralph Lauren", "categorie": "Pull", "taille": "M",
                                                         "couleur": "Gris", "etat": "tres_bon_etat", "defauts": "petite bouloche"})  # fmt: skip
    assert r.status_code == 200, r.text
    assert "lot" in r.json()["description"] and "bouloche" in r.json()["description"]
    db.refresh(a)
    assert a.etat == "tres_bon_etat" and a.titre_annonce == r.json()["titre"]
    r = client.post(f"/api/annonces/{a.id}/publier", json={"prix": "45"})
    assert (
        r.json()["statut"] == "en_ligne"
        and r.json()["date_publication"]
        and r.json()["prix_vente_cible"] == "45.00"
    )
    assert client.get("/api/annonces/a-publier").json() == []


def test_erreur_ia_conserve_la_fiche(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "anthropic_api_key", "")
    a = _article(db)
    r = client.post(f"/api/annonces/{a.id}/generer", json={"matiere": "Coton", "categorie": "Pull"})
    assert r.status_code == 502 and "ANTHROPIC_API_KEY" in r.json()["detail"]
    db.refresh(a)
    assert a.matiere == "Coton"


def test_messages_offre_et_suggestion(client: TestClient, db: Session, factice: None) -> None:
    a = _article(db, statut="en_ligne", prix_vente_cible=D("45"))
    db.add_all([
        Message(type="offre", acheteur="sophie", article_id=a.id, extrait="Je te propose 30 €", montant_offre=D("30"), statut="a_traiter"),
        Message(type="message", acheteur="tom", article_id=a.id, extrait="Toujours dispo ?", statut="a_traiter"),
        Message(type="message", acheteur="x", article_id=None, extrait="?", statut="a_traiter"),
    ])  # fmt: skip
    db.commit()
    groupes = client.get("/api/messages", params={"statut": "a_traiter"}).json()
    assert len(groupes) == 2
    groupe = next(g for g in groupes if g["article"])
    offre = next(m for m in groupe["messages"] if m["type"] == "offre")
    assert offre["analyse"]["decision"] == "contre_proposer" and offre["analyse"]["montant_propose"] == "38"
    r = client.post(f"/api/messages/{offre['id']}/suggestion").json()
    assert "38" in r["reponse_suggeree"]
    r = client.patch(
        f"/api/messages/{offre['id']}", json={"reponse_finale": "OK pour 38 €", "statut": "repondu"}
    ).json()
    assert r["statut"] == "repondu"
    assert len(client.get("/api/messages", params={"statut": "a_traiter"}).json()) == 2  # 2 restants


def test_crud_modeles(client: TestClient) -> None:
    r = client.post(
        "/api/modeles-reponse", json={"nom": "Merci", "contexte": "remerciement", "texte": "Merci !"}
    )
    assert r.status_code == 201
    mid = r.json()["id"]
    assert (
        client.put(
            f"/api/modeles-reponse/{mid}",
            json={"nom": "Merci", "contexte": "remerciement", "texte": "Merci beaucoup"},
        ).json()["texte"]
        == "Merci beaucoup"
    )
    assert client.delete(f"/api/modeles-reponse/{mid}").status_code == 204
    assert client.post("/api/modeles-annonce", json={"nom": "Pull", "categorie": "Pull"}).status_code == 201
    assert len(client.get("/api/modeles-annonce").json()) == 1
