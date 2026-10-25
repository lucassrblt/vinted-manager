"""Phase 2 : file de tâches, budget d'actions, arrêts, Telegram, surveillance et réglages."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_parametres
from app.models import CompteVinted, JournalVinted, TacheVinted
from app.services import extension, file_vinted, horaires, notifications, taches, telegram
from tests.outils_extension import LUCAS_VINTED, SOEUR_VINTED, FauxTelegram, a_heure, creer_compte, entetes

CHAT_LUCAS = "1001"
CHAT_SOEUR = "1002"


@pytest.fixture
def faux_telegram(monkeypatch: pytest.MonkeyPatch) -> FauxTelegram:
    faux = FauxTelegram()
    monkeypatch.setattr(telegram, "fabrique", lambda: faux)
    return faux


@pytest.fixture
def lucas(db: Session) -> tuple[CompteVinted, str]:
    compte, jeton = creer_compte(db, "Lucas", LUCAS_VINTED)
    compte.telegram_chat_id = CHAT_LUCAS
    db.commit()
    return compte, jeton


def _suivante(client: TestClient, jeton: str) -> dict[str, object] | None:
    r = client.get("/api/extension/taches/suivante", headers=entetes(jeton))
    assert r.status_code in (200, 204), r.text
    return r.json() if r.status_code == 200 else None


def _resultat(client: TestClient, jeton: str, tache_id: object, **corps: object) -> None:
    r = client.post(
        f"/api/extension/taches/{tache_id}/resultat", json={"ok": True} | corps, headers=entetes(jeton)
    )
    assert r.status_code == 204, r.text


def _tache(db: Session, compte: CompteVinted, type_tache: str, **kw: object) -> TacheVinted:
    t = taches.creer(db, compte, type_tache, {"texte": "Bonjour"} | dict(kw.pop("payload", {}) or {}), **kw)  # type: ignore[arg-type]
    db.commit()
    return t


def _journal(db: Session, type_entree: str) -> list[str]:
    return [j.message for j in db.scalars(select(JournalVinted).where(JournalVinted.type == type_entree))]


# --- File de tâches ---------------------------------------------------------------------------


def test_priorites_et_une_tache_a_la_fois(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    compte, jeton = lucas
    a_heure(monkeypatch, 14)
    prix = _tache(db, compte, "modifier_prix")
    reponse = _tache(db, compte, "repondre_message")
    offre = _tache(db, compte, "contre_offre")
    t = _suivante(client, jeton)
    assert t is not None and t["id"] == reponse.id and t["payload"] == {"texte": "Bonjour"}
    assert _suivante(client, jeton) is None  # une seule tâche en cours par compte
    _resultat(client, jeton, t["id"])
    t2 = _suivante(client, jeton)
    assert (
        t2 is not None and t2["id"] == offre.id
    )  # pas d'attente après une réponse : l'offre est urgente aussi
    _resultat(client, jeton, t2["id"])
    assert _suivante(client, jeton) is None  # action non urgente : 20 à 60 s d'écart
    a_heure(monkeypatch, 14, 2)
    t3 = _suivante(client, jeton)
    assert t3 is not None and t3["id"] == prix.id


def test_rien_de_futur_ni_de_l_autre_compte(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str]
) -> None:
    compte, jeton = lucas
    soeur, _ = creer_compte(db, "Sœur", SOEUR_VINTED)
    _tache(db, soeur, "repondre_message")
    _tache(db, compte, "repondre_message", executer_apres=horaires.maintenant() + timedelta(minutes=5))
    assert _suivante(client, jeton) is None


def test_la_nuit_seules_les_reponses_aux_acheteurs(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    compte, jeton = lucas
    a_heure(monkeypatch, 2)
    _tache(db, compte, "relance_favori")
    _tache(db, compte, "republication")
    reponse = _tache(db, compte, "repondre_message")
    offre = _tache(db, compte, "accepter_offre")
    vus = []
    for minute in (0, 1):
        a_heure(monkeypatch, 2, minute)
        t = _suivante(client, jeton)
        assert t is not None
        vus.append(t["id"])
        _resultat(client, jeton, t["id"])
    assert vus == [reponse.id, offre.id]
    a_heure(monkeypatch, 2, 5)
    assert _suivante(client, jeton) is None


def test_arret_d_urgence_global_module_et_pause(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    compte, jeton = lucas
    a_heure(monkeypatch, 14)
    _tache(db, compte, "repondre_message")
    assert client.put("/api/automatisation/global", json={"automatisation_active": False}).status_code == 200
    assert _suivante(client, jeton) is None
    client.put("/api/automatisation/global", json={"automatisation_active": True})
    client.put(f"/api/automatisation/comptes/{compte.id}/reglages", json={"modules": {"assistant": False}})
    assert _suivante(client, jeton) is None
    client.put(f"/api/automatisation/comptes/{compte.id}/reglages", json={"modules": {"assistant": True}})
    client.post(f"/api/automatisation/comptes/{compte.id}/pause")
    assert _suivante(client, jeton) is None
    client.post(f"/api/automatisation/comptes/{compte.id}/reprendre")
    assert _suivante(client, jeton) is not None  # rien n'a été perdu


def test_cle_unique_jamais_deux_fois_la_meme_action(db: Session, lucas: tuple[CompteVinted, str]) -> None:
    compte, _ = lucas
    a = taches.creer(db, compte, "accepter_offre", {"x": 1}, cle="offre:42")
    a.statut = "faite"
    b = taches.creer(db, compte, "accepter_offre", {"x": 2}, cle="offre:42")
    assert a.id == b.id and b.payload == {"x": 1}


def test_tache_perdue_passee_en_erreur_sans_nouvel_essai(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    compte, jeton = lucas
    a_heure(monkeypatch, 14)
    t = _tache(db, compte, "repondre_message")
    assert _suivante(client, jeton) is not None
    a_heure(monkeypatch, 14, 25)
    assert _suivante(client, jeton) is None
    db.refresh(t)
    assert t.statut == "erreur" and "interrompue" in (t.erreur or "") and t.tentatives == 1


# --- Erreurs et arrêts automatiques ----------------------------------------------------------


def test_trois_erreurs_vinted_consecutives_arretent_le_compte(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    monkeypatch: pytest.MonkeyPatch,
    faux_telegram: FauxTelegram,
) -> None:
    compte, jeton = lucas
    for i in range(4):
        _tache(db, compte, "repondre_message", payload={"i": i})
    # Une erreur « métier » (contrôle de l'extension) ne compte pas.
    for minute, vinted in enumerate((True, False, True, True)):
        a_heure(monkeypatch, 14, minute)
        t = _suivante(client, jeton)
        assert t is not None
        _resultat(client, jeton, t["id"], ok=False, erreur="Vinted a refusé (422)", erreur_vinted=vinted)
        db.refresh(compte)
        assert compte.pause is (minute == 3), minute
    assert "3 erreurs Vinted consécutives" in (compte.pause_raison or "")
    assert any("Compte arrêté" in m for m in faux_telegram.textes(CHAT_LUCAS))


def test_reponse_inattendue_arrete_et_previent_sur_telegram(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    monkeypatch: pytest.MonkeyPatch,
    faux_telegram: FauxTelegram,
) -> None:
    compte, jeton = lucas
    a_heure(monkeypatch, 14)
    t = _tache(db, compte, "repondre_message")
    assert _suivante(client, jeton) is not None
    _resultat(
        client, jeton, t.id, ok=False, erreur="Session Vinted expirée (401) : reconnecte-toi.", arret=True
    )
    db.refresh(compte)
    assert compte.pause
    texte = faux_telegram.textes(CHAT_LUCAS)[-1]
    assert "Session Vinted expirée" in texte and "Marche à suivre" in texte


# --- Budget ----------------------------------------------------------------------------------


def test_plafond_horaire_reporte_les_actions_non_urgentes(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    compte, jeton = lucas
    client.put(f"/api/automatisation/comptes/{compte.id}/reglages", json={"budget": {"actions_heure": 2}})
    db.refresh(compte)
    a_heure(monkeypatch, 14)
    for i in range(3):
        _tache(db, compte, "modifier_prix", payload={"i": i})
    faites = []
    for minute in (0, 2, 4):
        a_heure(monkeypatch, 14, minute)
        t = _suivante(client, jeton)
        if t:
            faites.append(t["id"])
            _resultat(client, jeton, t["id"])
    assert len(faites) == 2
    reportee = db.scalars(select(TacheVinted).where(TacheVinted.statut == "a_faire")).one()
    assert horaires.local(reportee.executer_apres).hour == 15
    # Une réponse à un acheteur n'est jamais retardée par le plafond horaire.
    _tache(db, compte, "repondre_message")
    assert _suivante(client, jeton) is not None


def test_plafond_journalier(
    client: TestClient, db: Session, lucas: tuple[CompteVinted, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    compte, jeton = lucas
    client.put(
        f"/api/automatisation/comptes/{compte.id}/reglages",
        json={"budget": {"offres_jour": 1, "messages_jour": 1}},
    )
    db.refresh(compte)
    a_heure(monkeypatch, 14)
    _tache(db, compte, "relance_favori")  # message + offre
    t = _suivante(client, jeton)
    assert t is not None
    _resultat(client, jeton, t["id"])
    a_heure(monkeypatch, 15)
    relance = _tache(db, compte, "relance_favori")
    assert _suivante(client, jeton) is None
    db.refresh(relance)
    assert horaires.local(relance.executer_apres).date() > horaires.local().date()  # demain
    # Une réponse d'acheteur au-delà du plafond : situation anormale, arrêt du compte.
    _tache(db, compte, "repondre_message")
    assert _suivante(client, jeton) is None
    db.refresh(compte)
    assert compte.pause and "Budget journalier" in (compte.pause_raison or "")


def test_budget_visible_dans_l_app(client: TestClient, db: Session, lucas: tuple[CompteVinted, str]) -> None:
    c = client.get("/api/automatisation/comptes").json()[0]
    assert c["budget_plafonds"] == {
        "brouillons": 6,
        "messages": 120,
        "offres": 60,
        "republications": 40,
        "heure": 15,
    }
    assert c["budget_utilise"]["heure"] == 0


# --- Telegram ----------------------------------------------------------------------------------


def test_appairage_par_code(client: TestClient, db: Session, faux_telegram: FauxTelegram) -> None:
    compte, _ = creer_compte(db, "Sœur", SOEUR_VINTED)
    code = client.post(f"/api/automatisation/comptes/{compte.id}/telegram").json()["telegram_code"]
    assert len(code) == 6 and code.isdigit()
    faux_telegram.ecrire(CHAT_SOEUR, "/start 000000" if code != "000000" else "/start 111111")
    faux_telegram.ecrire(CHAT_SOEUR, f"/start {code}")
    assert telegram.relever(db) == 2
    db.refresh(compte)
    assert compte.telegram_chat_id == CHAT_SOEUR and compte.telegram_code is None
    textes = faux_telegram.textes(CHAT_SOEUR)
    assert "expiré" in textes[0] and "Sœur" in textes[1]
    assert get_parametres(db).telegram_offset == 3
    assert client.get("/api/automatisation/comptes").json()[0]["telegram_relie"] is True


def test_commandes_stop_reprendre_etat(
    db: Session, lucas: tuple[CompteVinted, str], faux_telegram: FauxTelegram
) -> None:
    compte, _ = lucas
    faux_telegram.ecrire(CHAT_LUCAS, "/stop")
    telegram.relever(db)
    db.refresh(compte)
    assert compte.pause and "Telegram" in (compte.pause_raison or "")
    faux_telegram.ecrire(CHAT_LUCAS, "/etat")
    telegram.relever(db)
    assert "en pause" in faux_telegram.textes(CHAT_LUCAS)[-1]
    faux_telegram.ecrire(CHAT_LUCAS, "/reprendre")
    telegram.relever(db)
    db.refresh(compte)
    assert not compte.pause
    faux_telegram.ecrire("999", "/stop")  # chat inconnu : rien
    telegram.relever(db)
    assert "relié à aucun compte" in faux_telegram.textes("999")[0]


def test_boutons_envoyer_modifier_ignorer(
    db: Session, lucas: tuple[CompteVinted, str], faux_telegram: FauxTelegram, monkeypatch: pytest.MonkeyPatch
) -> None:
    compte, _ = lucas
    a_heure(monkeypatch, 14)
    envoyer = _tache(db, compte, "repondre_message", statut="a_valider")
    modifier = _tache(db, compte, "repondre_message", statut="a_valider")
    ignorer = _tache(db, compte, "repondre_message", statut="a_valider")
    faux_telegram.cliquer(CHAT_LUCAS, f"t:{envoyer.id}:envoyer")
    faux_telegram.cliquer(CHAT_LUCAS, f"t:{ignorer.id}:ignorer")
    faux_telegram.cliquer(CHAT_LUCAS, f"t:{modifier.id}:modifier")
    faux_telegram.ecrire(CHAT_LUCAS, "Oui, il est toujours disponible !")
    faux_telegram.cliquer("999", f"t:{envoyer.id}:envoyer")  # autre chat : refusé
    telegram.relever(db)
    for t in (envoyer, modifier, ignorer):
        db.refresh(t)
    assert envoyer.statut == "a_faire" and envoyer.executer_apres > horaires.maintenant()
    assert ignorer.statut == "annulee"
    assert modifier.statut == "a_faire" and modifier.payload["texte"] == "Oui, il est toujours disponible !"
    assert [r for _, r in faux_telegram.reponses_boutons] == [
        "Envoi programmé.",
        "Ignorée.",
        "J'attends ta réponse.",
        "Tâche introuvable.",
    ]


def test_validation_depuis_l_app(client: TestClient, db: Session, lucas: tuple[CompteVinted, str]) -> None:
    compte, _ = lucas
    t = _tache(db, compte, "repondre_message", statut="a_valider")
    r = client.post(f"/api/automatisation/taches/{t.id}/valider", json={"texte": "Texte corrigé"})
    assert r.json()["statut"] == "a_faire" and r.json()["payload"]["texte"] == "Texte corrigé"
    assert client.post(f"/api/automatisation/taches/{t.id}/annuler").json()["statut"] == "annulee"
    assert client.get("/api/automatisation/taches", params={"statut": "annulee"}).json()[0]["id"] == t.id


def test_sans_token_telegram_rien_n_est_envoye(db: Session, lucas: tuple[CompteVinted, str]) -> None:
    compte, _ = lucas
    assert telegram.fabrique() is None
    from app.services import alertes

    alertes.alerter(db, compte, "arret", "Test")
    alertes.valider(db)  # aucune erreur
    assert telegram.relever(db) == 0


def test_alertes_silencieuses_la_nuit_et_filtrees_par_type(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    faux_telegram: FauxTelegram,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.services import alertes

    compte, _ = lucas
    a_heure(monkeypatch, 3)
    alertes.alerter(db, compte, "hors_ligne", "Extension hors ligne")
    alertes.valider(db)
    assert faux_telegram.messages[-1]["silencieux"] is True
    client.put(
        f"/api/automatisation/comptes/{compte.id}/reglages",
        json={"notifications": {"types": {"hors_ligne": False}}},
    )
    db.refresh(compte)
    alertes.alerter(db, compte, "hors_ligne", "Encore")
    alertes.valider(db)
    assert len(faux_telegram.messages) == 1


def test_vente_relayee_sur_le_chat_du_compte(
    db: Session, lucas: tuple[CompteVinted, str], faux_telegram: FauxTelegram
) -> None:
    compte, _ = lucas
    soeur, _ = creer_compte(db, "Sœur", SOEUR_VINTED)
    soeur.telegram_chat_id = CHAT_SOEUR
    db.commit()
    notifications.notifier(db, "vente", "🛍️ Vendu : Robe", "/", corps="20 €", compte_id=soeur.id)
    notifications.notifier(db, "offre", "Offre", "/")  # pas relayée
    db.commit()
    notifications.envoyer_en_attente(db)
    assert faux_telegram.textes() == ["🛍️ Vendu : Robe\n20 €"]
    assert faux_telegram.messages[0]["chat_id"] == CHAT_SOEUR


# --- Surveillance --------------------------------------------------------------------------------


def test_hors_ligne_puis_de_retour(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    faux_telegram: FauxTelegram,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    compte, jeton = lucas
    a_heure(monkeypatch, 14)
    client.post(
        "/api/extension/heartbeat",
        json={"vinted_user_id": LUCAS_VINTED, "onglet": True},
        headers=entetes(jeton),
    )
    a_heure(monkeypatch, 14, 4)
    db.expire_all()
    extension.surveiller(db)
    assert not faux_telegram.messages
    a_heure(monkeypatch, 14, 6)
    db.expire_all()
    extension.surveiller(db)
    extension.surveiller(db)
    assert len([m for m in faux_telegram.textes() if "hors ligne" in m]) == 1
    client.post(
        "/api/extension/heartbeat",
        json={"vinted_user_id": LUCAS_VINTED, "onglet": True},
        headers=entetes(jeton),
    )
    assert "de nouveau en ligne" in faux_telegram.textes()[-1]


def test_onglet_vinted_ferme(
    client: TestClient,
    db: Session,
    lucas: tuple[CompteVinted, str],
    faux_telegram: FauxTelegram,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, jeton = lucas
    for minute in range(0, 7):
        a_heure(monkeypatch, 14, minute)
        client.post("/api/extension/heartbeat", json={"onglet": False}, headers=entetes(jeton))
        db.expire_all()
        extension.surveiller(db)
    assert [m for m in faux_telegram.textes() if "Onglet Vinted fermé" in m]


# --- Réglages ------------------------------------------------------------------------------------


def test_reglages_par_compte(client: TestClient, db: Session, lucas: tuple[CompteVinted, str]) -> None:
    compte, jeton = lucas
    r = client.get(f"/api/automatisation/comptes/{compte.id}/reglages").json()
    assert r["favoris"]["reduction_pct"] == 10 and r["assistant"]["seuil_acceptation_pct"] == 90
    assert r["prix"]["plancher_pct"] == 82 and r["apres_vente"]["heure_recap"] == "17:30"
    r = client.put(f"/api/automatisation/comptes/{compte.id}/reglages", json={"heures": {"debut": 9}}).json()
    assert r["heures"] == {"debut": 9, "fin": 23}
    for invalide in (
        {"heures": {"debut": 23}},
        {"budget": {"actions_heure": -1}},
        {"inconnu": 1},
        {"favoris": {"messages": []}} | {"favoris": {"messages": [""]}},
    ):
        assert (
            client.put(f"/api/automatisation/comptes/{compte.id}/reglages", json=invalide).status_code == 422
        )
    assert client.get("/api/extension/compte", headers=entetes(jeton)).json()["heure_debut"] == 9


def test_resume_etat(db: Session, lucas: tuple[CompteVinted, str]) -> None:
    compte, _ = lucas
    texte = file_vinted.resume_etat(db, compte)
    assert texte.startswith("Lucas : ▶️ actif") and "0/6 brouillons" in texte
