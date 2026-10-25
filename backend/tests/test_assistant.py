"""Phase 3 : assistant (messages et offres reçues) et lecture du dressing, à partir des captures réelles."""

import copy
import json
from datetime import timedelta
from decimal import Decimal as D
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, CompteVinted, ConversationVinted, TacheVinted
from app.models.enums import StatutArticle
from app.services import horaires, ia, offres, telegram
from tests.outils_extension import LUCAS_VINTED, FauxTelegram, a_heure, creer_compte, entetes

CAPTURES = Path(__file__).resolve().parents[2] / "extension" / "tests" / "fixtures" / "vinted"
CONV_ID = "01a16aa3-daff-79bb-a570-c156d97cb288"
ACHETEUR = "900000014"
ITEM_UNIQLO = 10475120267
CHAT = "1001"


def capture(nom: str) -> Any:
    return json.loads((CAPTURES / f"{nom}.json").read_text())["response"]["body"]


@pytest.fixture
def telegram_faux(monkeypatch: pytest.MonkeyPatch) -> FauxTelegram:
    faux = FauxTelegram()
    monkeypatch.setattr(telegram, "fabrique", lambda: faux)
    return faux


@pytest.fixture
def ia_simulee(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """L'IA répond ce que le test prépare dans la liste (dernier élément), et note les appels."""
    reponses: list[dict[str, Any]] = [{"intention": "question", "reponse": "Oui, toujours disponible !"}]
    appels: list[dict[str, Any]] = []

    def repondre(messages: list[str], fiche: Any, ton: str = "", types: Any = None) -> ia.ReponseAssistant:
        appels.append({"messages": messages, "fiche": fiche})
        r = reponses[-1]
        if isinstance(r, Exception):
            raise r
        return ia.ReponseAssistant(**r)

    monkeypatch.setattr(ia, "repondre_acheteur", repondre)
    monkeypatch.setattr(
        ia, "suggerer_reponse", lambda *a, **k: "Merci pour ton offre, mais c'est un peu bas pour moi."
    )
    appels.append({"reponses": reponses})
    return appels


@pytest.fixture
def lucas(db: Session) -> tuple[CompteVinted, str]:
    compte, jeton = creer_compte(db, "Lucas", LUCAS_VINTED)
    compte.telegram_chat_id = CHAT
    db.commit()
    return compte, jeton


@pytest.fixture
def sweat(db: Session, lucas: tuple[CompteVinted, str]) -> Article:
    """L'article de la conversation capturée, en ligne à 7 €."""
    a = Article(
        nom="Sweat col rond Uniqlo gris chiné taille L",
        marque="Uniqlo",
        taille="L",
        etat="bon_etat",
        defauts="petite tache légère sur le devant en bas",
        statut=StatutArticle.EN_LIGNE,
        compte_id=lucas[0].id,
        prix_vente_cible=D("7"),
        prix_initial=D("7"),
        vinted_item_id=ITEM_UNIQLO,
    )
    db.add(a)
    db.commit()
    return a


def evenement(client: TestClient, jeton: str, type_evt: str, donnees: Any) -> dict[str, Any]:
    r = client.post(
        "/api/extension/evenements", json={"type": type_evt, "donnees": donnees}, headers=entetes(jeton)
    )
    assert r.status_code == 200, r.text
    return r.json()


def inbox(derniere: str | None = None, expediteur: str = "0") -> dict[str, Any]:
    corps = copy.deepcopy(capture("messaging_inbox"))
    if derniere:
        for c in corps["conversations"]:
            if c["id"] == CONV_ID:
                c["last_message"]["created_at"] = derniere
                c["last_message"]["sender_id"] = expediteur
    return corps


def conversation(*nouveaux: dict[str, Any]) -> dict[str, Any]:
    corps = copy.deepcopy(capture("messaging_conversation"))
    corps["messages"] += list(nouveaux)
    return corps


def message_texte(texte: str, quand: str, mid: str = "m-texte") -> dict[str, Any]:
    return {
        "conversation_id": CONV_ID,
        "created_at": quand,
        "data": {"entity": {"body": texte, "user_id": int(ACHETEUR)}, "entity_type": "message"},
        "id": mid,
        "message_type": "legacy_reply",
        "sender_id": ACHETEUR,
    }


def message_offre(montant: str, quand: str, demande: int = 6000000001, statut: int = 10) -> dict[str, Any]:
    return {
        "conversation_id": CONV_ID,
        "created_at": quand,
        "data": {
            "entity": {
                "offer_request_id": demande,
                "price": {"amount": montant, "currency_code": "EUR"},
                "original_price": {"amount": "7.0", "currency_code": "EUR"},
                "status": statut,
                "transaction_id": 23517428140,
                "user_id": int(ACHETEUR),
                "current": True,
            },
            "entity_type": "offer_request_message",
        },
        "id": f"m-offre-{demande}",
        "message_type": "legacy_offer_request",
        "sender_id": ACHETEUR,
    }


def iso(minutes: int = 0) -> str:
    return (horaires.maintenant() + timedelta(minutes=minutes)).astimezone().isoformat()


def taches_de(db: Session, **filtres: Any) -> list[TacheVinted]:
    q = select(TacheVinted).order_by(TacheVinted.id)
    for k, v in filtres.items():
        q = q.where(getattr(TacheVinted, k) == v)
    return list(db.scalars(q))


@pytest.fixture
def initialise(client: TestClient, lucas: tuple[CompteVinted, str], monkeypatch: pytest.MonkeyPatch) -> None:
    """Première lecture de la messagerie à 14 h : rien d'antérieur n'est traité."""
    a_heure(monkeypatch, 14)
    assert evenement(client, lucas[1], "inbox", inbox()) == {"a_lire": []}
    a_heure(monkeypatch, 14, 5)


# --- Règles d'offre (section 8) ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("offre", "dernier", "renvoye", "attendu"),
    [
        ("18", None, False, ("accepter", "18")),  # 90 % de 20
        ("9", None, False, ("refuser", None)),  # moins de 50 %
        ("12", None, False, ("contre", "16.50")),  # milieu 16, plancher 16,50
        ("14", "16.50", False, ("contre", "16.50")),  # déjà au plancher : renvoyé une fois
        ("15", "16.50", True, ("escalade", None)),  # puis Lucas décide
        ("16.5", "16.50", True, ("accepter", "16.5")),  # offre ≥ dernière proposition
        ("15", "19", False, ("contre", "17.00")),  # milieu de l'offre et de la dernière proposition
    ],
)
def test_regles_offre(
    offre: str, dernier: str | None, renvoye: bool, attendu: tuple[str, str | None]
) -> None:
    d = offres.decider_vinted(D(offre), D("20"), D("20"), D(dernier) if dernier else None, renvoye)
    assert (d.action, str(d.montant) if d.montant is not None else None) == attendu
    assert d.plancher == D("16.50")


def test_contre_offre_jamais_au_dessus_de_la_precedente_ni_sous_le_plancher() -> None:
    dernier = D("20")
    for offre in ("12", "13", "14", "15", "16", "16"):
        d = offres.decider_vinted(D(offre), D("20"), D("20"), dernier, False)
        if d.action != "contre":
            break
        assert d.montant is not None and D("16.50") <= d.montant <= dernier
        dernier = d.montant


def test_contre_offre_inferieure_a_l_offre_devient_acceptation() -> None:
    d = offres.decider_vinted(D("17"), D("19"), D("19"), D("17.30"), False)
    assert d.action == "accepter"


# --- Messagerie ---------------------------------------------------------------------------------


def test_premiere_lecture_ne_traite_rien_puis_reprise(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str], sweat: Article, initialise: None
) -> None:
    compte, jeton = lucas
    convs = db.scalars(select(ConversationVinted)).all()
    assert {c.id for c in convs} >= {CONV_ID} and all(c.dernier_traite_le for c in convs)
    conv = db.get(ConversationVinted, CONV_ID)
    assert conv is not None and conv.article_id == sweat.id and conv.interlocuteur_login == "membre_test_10"
    # Nouveau message de l'acheteur : à lire. Message du compte lui-même : rien à lire.
    assert evenement(client, jeton, "inbox", inbox(iso(), ACHETEUR)) == {"a_lire": [CONV_ID]}
    assert evenement(client, jeton, "inbox", inbox(iso(1), str(LUCAS_VINTED))) == {"a_lire": []}


def test_offre_recue_contre_proposee(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    sweat: Article,
    initialise: None,
    ia_simulee: Any,
) -> None:
    _, jeton = lucas
    assert evenement(client, jeton, "conversation", conversation(message_offre("5.0", iso()))) == {
        "traite": 1
    }
    t = taches_de(db)[0]
    assert (t.type, t.statut, t.priorite) == ("contre_offre", "a_faire", 2)
    # 7 € affiché, offre 5 € : milieu 6 €, plancher 82 % de 7 € = 6 €.
    assert t.payload == {
        "conversation_id": CONV_ID,
        "transaction_id": 23517428140,
        "offer_request_id": 6000000001,
        "article": sweat.nom,
        "offre": "5",
        "montant": "6",
        "renvoi_plancher": False,
    }
    assert timedelta(seconds=20) <= t.executer_apres - horaires.maintenant() <= timedelta(seconds=60)
    # Le même événement relu ne crée rien de plus.
    assert evenement(client, jeton, "conversation", conversation(message_offre("5.0", iso()))) == {
        "traite": 0
    }
    assert len(taches_de(db)) == 1


def test_offre_acceptee_des_90_pourcent(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str], sweat: Article, initialise: None
) -> None:
    evenement(client, lucas[1], "conversation", conversation(message_offre("6.5", iso(), demande=77)))
    t = taches_de(db)[0]
    assert t.type == "accepter_offre" and t.payload["offer_request_id"] == 77 and t.cle == "offre:77"


def test_offre_ridicule_refusee_avec_message(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    sweat: Article,
    initialise: None,
    ia_simulee: Any,
) -> None:
    evenement(client, lucas[1], "conversation", conversation(message_offre("3.0", iso())))
    t = taches_de(db)[0]
    assert t.type == "refuser_offre" and t.payload["texte"].startswith("Merci pour ton offre")


def test_offre_deja_traitee_ou_ancienne_ignoree(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str], sweat: Article, initialise: None
) -> None:
    # La capture contient une offre acceptée (statut 20) et un message du compte : rien à faire.
    assert evenement(client, lucas[1], "conversation", conversation()) == {"traite": 0}
    evenement(client, lucas[1], "conversation", conversation(message_offre("5.0", iso(), statut=20)))
    assert not taches_de(db)


def test_negociation_jusqu_au_plancher_puis_escalade(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    sweat: Article,
    initialise: None,
    telegram_faux: FauxTelegram,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compte, jeton = lucas
    sweat.prix_vente_cible = sweat.prix_initial = D("20")
    db.commit()
    montants = []
    for tour, offre in enumerate(("12", "14", "15")):
        a_heure(monkeypatch, 14, 10 + tour * 5)
        evenement(
            client, jeton, "conversation", conversation(message_offre(offre, iso(), demande=100 + tour))
        )
        t = taches_de(db)[-1]
        montants.append((t.type, t.statut, t.payload.get("montant")))
        if t.statut == "a_faire":  # l'extension exécute la contre-offre
            a_heure(monkeypatch, 14, 11 + tour * 5)
            r = client.get("/api/extension/taches/suivante", headers=entetes(jeton)).json()
            client.post(
                f"/api/extension/taches/{r['id']}/resultat", json={"ok": True}, headers=entetes(jeton)
            )
    assert montants == [
        ("contre_offre", "a_faire", "16.5"),
        ("contre_offre", "a_faire", "16.5"),  # plancher renvoyé une fois
        ("accepter_offre", "a_valider", "15"),  # puis Lucas décide
    ]
    alerte = telegram_faux.messages[-1]
    assert "Offre à décider" in str(alerte["texte"]) and alerte["boutons"]
    assert [b["text"] for b in alerte["boutons"][0]] == ["✅ Envoyer", "🚫 Ignorer"]  # type: ignore[index]


def test_message_question_repondu_automatiquement(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    sweat: Article,
    initialise: None,
    ia_simulee: Any,
) -> None:
    evenement(
        client,
        lucas[1],
        "conversation",
        conversation(message_texte("Bonjour, il est toujours dispo ?", iso())),
    )
    t = taches_de(db)[0]
    assert (t.type, t.statut, t.priorite) == ("repondre_message", "a_faire", 1)
    assert t.payload["texte"] == "Oui, toujours disponible !"
    fiche = ia_simulee[-1]["fiche"]
    assert fiche["defauts"] == "petite tache légère sur le devant en bas" and fiche["taille"] == "L"


@pytest.mark.parametrize(
    "texte",
    [
        "Je peux te payer par PayPal entre amis ?",
        "Tu peux me donner ton numéro whatsapp ?",
        "Quelle est la longueur du sweat ?",
        "Je fais un lot avec ton jean ?",
        "Je n'ai jamais reçu le colis, je veux un remboursement",
    ],
)
def test_escalade_obligatoire_meme_si_l_ia_est_confiante(
    texte: str,
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    sweat: Article,
    initialise: None,
    ia_simulee: Any,
    telegram_faux: FauxTelegram,
) -> None:
    evenement(client, lucas[1], "conversation", conversation(message_texte(texte, iso())))
    t = taches_de(db)[0]
    assert t.statut == "a_valider" and t.payload["raison_escalade"].startswith("Message à relire")
    assert t.payload["texte"] == "Oui, toujours disponible !"  # proposition à relire
    alerte = telegram_faux.messages[-1]
    assert "Intervention requise" in str(alerte["texte"]) and texte[:20] in str(alerte["texte"])
    assert len(alerte["boutons"][0]) == 3  # type: ignore[index]


def test_escalade_demandee_par_l_ia(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    sweat: Article,
    initialise: None,
    ia_simulee: Any,
) -> None:
    ia_simulee[0]["reponses"].append(
        {
            "intention": "suspect",
            "reponse": "Je vérifie.",
            "escalade": True,
            "raison_escalade": "Demande étrange.",
        }
    )
    evenement(
        client,
        lucas[1],
        "conversation",
        conversation(message_texte("Envoie-moi le code reçu par SMS", iso())),
    )
    t = taches_de(db)[0]
    assert t.statut == "a_valider" and "suspect" in t.payload["raison_escalade"]


def test_prix_propose_dans_un_message(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    sweat: Article,
    initialise: None,
    ia_simulee: Any,
) -> None:
    ia_simulee[0]["reponses"].append({"intention": "offre_texte", "reponse": "…", "montant_propose": 6})
    evenement(
        client, lucas[1], "conversation", conversation(message_texte("Tu me la laisses à 6 € ?", iso()))
    )
    t = taches_de(db)[0]
    # 6 € sur 7 € affichés : milieu 6,50 € → offre vendeur à 6,50 € sur la transaction de la conversation.
    assert (t.type, t.payload["montant"], t.payload["transaction_id"]) == ("contre_offre", "6.5", 23517428140)


def test_ia_indisponible_escalade_sans_bouton_envoyer(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    sweat: Article,
    initialise: None,
    ia_simulee: Any,
    telegram_faux: FauxTelegram,
) -> None:
    ia_simulee[0]["reponses"].append(ia.ErreurIA("Crédit API Anthropic épuisé."))
    evenement(client, lucas[1], "conversation", conversation(message_texte("Bonjour !", iso())))
    t = taches_de(db)[0]
    assert t.statut == "a_valider" and "IA indisponible" in t.payload["raison_escalade"]
    assert [b["text"] for b in telegram_faux.messages[-1]["boutons"][0]] == ["✏️ Modifier", "🚫 Ignorer"]  # type: ignore[index]


def test_reponse_la_nuit_en_5_a_15_minutes(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    sweat: Article,
    ia_simulee: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    a_heure(monkeypatch, 1)
    evenement(
        client, lucas[1], "inbox", inbox(iso(-60), str(LUCAS_VINTED))
    )  # captures datées de 10 h : recalées
    a_heure(monkeypatch, 1, 30)
    corps = conversation()
    corps["messages"] = [message_texte("Bonsoir, dispo ?", iso())]  # captures datées de 10 h : retirées
    evenement(client, lucas[1], "conversation", corps)
    t = taches_de(db)[0]
    assert timedelta(minutes=5) <= t.executer_apres - horaires.maintenant() <= timedelta(minutes=15)


def test_nouveau_message_remplace_la_reponse_en_attente(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    sweat: Article,
    initialise: None,
    ia_simulee: Any,
) -> None:
    evenement(client, lucas[1], "conversation", conversation(message_texte("Bonjour", iso(), "m1")))
    evenement(
        client,
        lucas[1],
        "conversation",
        conversation(message_texte("Bonjour", iso(), "m1"), message_texte("Il est dispo ?", iso(1), "m2")),
    )
    statuts = [t.statut for t in taches_de(db)]
    assert statuts == ["annulee", "a_faire"]
    assert ia_simulee[-1]["messages"] == ["Il est dispo ?"]


def test_reponse_manuelle_annule_la_reponse_prevue(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    sweat: Article,
    initialise: None,
    ia_simulee: Any,
) -> None:
    evenement(client, lucas[1], "conversation", conversation(message_texte("Bonjour", iso())))
    evenement(client, lucas[1], "inbox", inbox(iso(2), str(LUCAS_VINTED)))  # Lucas a répondu lui-même
    assert [t.statut for t in taches_de(db)] == ["annulee"]


def test_article_inconnu_escalade(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str], initialise: None, ia_simulee: Any
) -> None:
    evenement(client, lucas[1], "conversation", conversation(message_texte("Bonjour", iso())))
    evenement(client, lucas[1], "conversation", conversation(message_offre("5.0", iso(1))))
    t = taches_de(db)
    assert len(t) == 1 and t[0].statut == "a_valider" and "non rattaché" in t[0].payload["raison_escalade"]


def test_resultat_contre_offre_memorise_la_derniere_proposition(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    sweat: Article,
    initialise: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, jeton = lucas
    evenement(client, jeton, "conversation", conversation(message_offre("5.0", iso())))
    a_heure(monkeypatch, 14, 7)
    t = client.get("/api/extension/taches/suivante", headers=entetes(jeton)).json()
    client.post(
        f"/api/extension/taches/{t['id']}/resultat",
        json={"ok": True, "resultat": {"offer_id": 1}},
        headers=entetes(jeton),
    )
    db.expire_all()
    conv = db.get(ConversationVinted, CONV_ID)
    assert conv is not None and conv.dernier_propose == D("6")


# --- Dressing -------------------------------------------------------------------------------------


def test_dressing_rattache_importe_et_ignore_les_brouillons(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str]
) -> None:
    compte, jeton = lucas
    items = capture("wardrobe_items")["items"]
    publie = Article(
        nom="Maillot", statut=StatutArticle.RECU_A_PUBLIER, compte_id=compte.id, vinted_draft_id=10495469586
    )
    db.add(publie)
    db.commit()
    reponse = evenement(client, jeton, "dressing", {"items": items, "complet": True})
    assert reponse == {"rattaches": 0, "importes": 1}  # 3 brouillons ignorés, 1 annonce en ligne importée
    importe = db.scalars(select(Article).where(Article.importe_vinted.is_(True))).one()
    assert (importe.nom, importe.vinted_item_id, importe.prix_vente_cible, importe.prix_initial) == (
        "Sweat demi-zip Autograph gris taille M",
        10495633803,
        D("10.00"),
        D("10.00"),
    )
    assert (
        importe.statut == StatutArticle.EN_LIGNE
        and importe.etat == "tres_bon_etat"
        and importe.compte_id == compte.id
    )
    assert importe.prix_plancher == D("8.50") and importe.vinted_photos and importe.vinted_favoris == 0
    # Relu : rattaché par vinted_item_id, rien de nouveau.
    assert evenement(client, jeton, "dressing", {"items": items, "complet": True}) == {
        "rattaches": 1,
        "importes": 0,
    }


def test_dressing_rattache_par_titre_et_brouillon_publie(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str]
) -> None:
    compte, jeton = lucas
    par_titre = Article(
        nom="Sweat Autograph",
        titre_annonce="Sweat demi-zip Autograph gris taille M",
        statut=StatutArticle.RECU_A_PUBLIER,
        compte_id=compte.id,
        prix_vente_cible=D("12"),
    )
    brouillon = Article(
        nom="T-shirt", statut=StatutArticle.RECU_A_PUBLIER, compte_id=compte.id, vinted_draft_id=555
    )
    db.add_all([par_titre, brouillon])
    db.commit()
    items = [
        {
            "id": 10495633803,
            "title": "Sweat demi-zip Autograph gris taille M",
            "is_draft": False,
            "price": {"amount": "10.0"},
        },
        {"id": 555, "title": "Titre modifié par Lucas", "is_draft": False, "price": {"amount": "24.0"}},
    ]
    assert evenement(client, jeton, "dressing", {"items": items}) == {"rattaches": 2, "importes": 0}
    db.expire_all()
    assert (par_titre.vinted_item_id, par_titre.statut, par_titre.prix_vente_cible) == (
        10495633803,
        "en_ligne",
        D("10.00"),
    )
    assert par_titre.prix_initial == D("10.00")
    assert (brouillon.vinted_item_id, brouillon.statut) == (555, "en_ligne")


def test_evenement_inconnu(client: TestClient, lucas: tuple[CompteVinted, str]) -> None:
    r = client.post("/api/extension/evenements", json={"type": "inconnu"}, headers=entetes(lucas[1]))
    assert r.status_code == 422


def test_point_de_reprise_et_reponse_manuelle_lue_dans_la_conversation(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    sweat: Article,
    initialise: None,
    ia_simulee: Any,
) -> None:
    evenement(client, lucas[1], "conversation", conversation(message_texte("Bonjour", iso())))
    # L'inbox n'indique jamais l'auteur (sender_id « 0 ») : c'est la conversation qui montre la réponse manuelle.
    reponse_lucas = {
        "conversation_id": CONV_ID, "created_at": iso(2), "id": "m-lucas", "message_type": "reply_plain",
        "sender_id": str(LUCAS_VINTED), "data": {"content": "Oui !"},
    }  # fmt: skip
    evenement(client, lucas[1], "conversation", conversation(message_texte("Bonjour", iso()), reponse_lucas))
    assert [t.statut for t in taches_de(db)] == ["annulee"]
    conv = db.get(ConversationVinted, CONV_ID)
    assert conv is not None and conv.dernier_traite_le is not None
    # Inbox dont la date est celle du dernier message déjà traité : rien à relire.
    assert evenement(client, lucas[1], "inbox", inbox(conv.dernier_traite_le.isoformat())) == {"a_lire": []}
