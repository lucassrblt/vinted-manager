"""Phase 1 : socle de l'extension et brouillons automatiques (tests de réception 1 à 5)."""

import io
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_parametres
from app.models import Article, CompteVinted, JournalVinted, PhotoArticle
from app.services import brouillons, couleur
from tests.outils_extension import (
    LUCAS_VINTED,
    SOEUR_VINTED,
    a_heure,
    article_pret,
    creer_compte,
    entetes,
    heartbeat,
    jpeg,
)


@pytest.fixture
def journee(monkeypatch: pytest.MonkeyPatch) -> None:
    a_heure(monkeypatch, 14)


def _suivant(client: TestClient, jeton: str) -> dict[str, object] | None:
    r = client.get("/api/extension/brouillons/suivant", headers=entetes(jeton))
    assert r.status_code in (200, 204), r.text
    return r.json() if r.status_code == 200 else None


def _alertes(db: Session, type_alerte: str) -> list[JournalVinted]:
    return list(db.scalars(select(JournalVinted).where(JournalVinted.type == type_alerte)))


# --- Authentification -------------------------------------------------------------------------


def test_jeton_obligatoire_et_stocke_hashe(anonyme: TestClient, db: Session) -> None:
    compte, jeton = creer_compte(db, "Lucas", LUCAS_VINTED)
    assert anonyme.get("/api/extension/compte").status_code == 401
    assert anonyme.get("/api/extension/compte", headers=entetes("vmx_faux")).status_code == 401
    r = anonyme.get("/api/extension/compte", headers=entetes(jeton))
    assert r.json() | {"heures_actives": None} == {
        "compte_id": compte.id,
        "nom": "Lucas",
        "vinted_user_id": LUCAS_VINTED,
        "pause": False,
        "pause_raison": None,
        "brouillons_du_jour": 0,
        "brouillons_max_jour": 6,
        "automatisation_active": True,
        "heures_actives": None,
        "heure_debut": 8,
        "heure_fin": 23,
        "modules": dict.fromkeys(
            ("brouillons", "assistant", "favoris", "republication", "prix", "apres_vente"), True
        ),
    }
    assert compte.jeton_extension_hash != jeton and len(compte.jeton_extension_hash or "") == 64


def test_generer_un_jeton_depuis_l_app_invalide_l_ancien(client: TestClient, db: Session) -> None:
    compte, ancien = creer_compte(db, "Lucas", LUCAS_VINTED)
    nouveau = client.post(f"/api/automatisation/comptes/{compte.id}/jeton").json()["jeton"]
    assert client.get("/api/extension/compte", headers=entetes(ancien)).status_code == 401
    assert client.get("/api/extension/compte", headers=entetes(nouveau)).status_code == 200


def test_compte_sans_boite_mail_et_confirmation_du_compte_vu(client: TestClient, db: Session) -> None:
    c = client.post("/api/automatisation/comptes", json={"nom": "Sœur"}).json()
    assert c["imap_configure"] is False and c["vinted_user_id"] is None
    jeton = client.post(f"/api/automatisation/comptes/{c['id']}/jeton").json()["jeton"]
    heartbeat(client, jeton, SOEUR_VINTED, "soeur")
    r = client.patch(f"/api/automatisation/comptes/{c['id']}", json={"confirmer_compte_vu": True})
    assert r.json()["vinted_user_id"] == SOEUR_VINTED and r.json()["vinted_login_vu"] == "soeur"
    assert client.get("/api/automatisation/comptes").json()[0]["extension_vue_le"] is not None


# --- Test de réception 1 : un article complet devient un brouillon ----------------------------


def test_article_complet_devient_un_brouillon(client: TestClient, db: Session, journee: None) -> None:
    compte, jeton = creer_compte(db, "Lucas", LUCAS_VINTED)
    a = article_pret(db, compte, types=("dos", "etiquette", "devant", "logo", "detail", "defaut"))
    heartbeat(client, jeton, LUCAS_VINTED)

    charge = _suivant(client, jeton)
    assert charge is not None
    assert {k: charge[k] for k in ("article_id", "titre", "prix", "marque", "taille", "condition_id")} == {
        "article_id": a.id,
        "titre": "T-shirt Nike ACG violet taille M",
        "prix": "24",
        "marque": "Nike ACG",
        "taille": "M",
        "condition_id": 6,
    }
    assert charge["package_size_id"] == 1 and charge["ai_photo"] is True
    assert [p["type"] for p in charge["photos"]] == ["devant", "dos", "etiquette", "logo", "detail", "defaut"]
    db.refresh(a)
    assert a.brouillon_statut == "en_cours"
    assert _suivant(client, jeton) is None  # un seul brouillon à la fois

    # Première photo réelle : la photo « devant » publiée est l'originale (violette), pas la retouche.
    devant = charge["photos"][0]["photo_id"]
    r = client.get(f"/api/extension/photos/{devant}", headers=entetes(jeton))
    assert r.headers["content-type"] == "image/jpeg"
    pixel = Image.open(io.BytesIO(r.content)).getpixel((300, 400))
    assert isinstance(pixel, tuple) and abs(pixel[0] - 120) < 8 and abs(pixel[2] - 180) < 8

    r = client.post(
        f"/api/extension/brouillons/{a.id}/resultat",
        json={"ok": True, "vinted_draft_id": 10522041322, "ai_photo": True},
        headers=entetes(jeton),
    )
    assert r.status_code == 204, r.text
    db.refresh(a)
    assert (a.brouillon_statut, a.vinted_draft_id, a.ai_photo_declare) == ("cree", 10522041322, True)
    assert a.prix_initial == D("24") and a.prix_plancher == D("20")  # 82 % de 24 = 19,68 → 20
    assert _alertes(db, "brouillon_pret")


def test_ai_photo_faux_seulement_si_aucune_photo_generee(
    client: TestClient, db: Session, journee: None
) -> None:
    compte, jeton = creer_compte(db, "Lucas", LUCAS_VINTED)
    a = article_pret(db, compte)
    for p in db.scalars(select(PhotoArticle).where(PhotoArticle.article_id == a.id)):
        p.version_choisie = "original"
    db.commit()
    charge = _suivant(client, jeton)
    assert charge is not None and charge["ai_photo"] is False


# --- Test de réception 2 : jamais l'article de l'autre compte ---------------------------------


def test_article_de_la_soeur_jamais_traite_par_le_profil_de_lucas(
    client: TestClient, db: Session, journee: None
) -> None:
    lucas, jeton_lucas = creer_compte(db, "Lucas", LUCAS_VINTED)
    soeur, jeton_soeur = creer_compte(db, "Sœur", SOEUR_VINTED)
    a_soeur = article_pret(db, soeur, nom="Robe Zara")
    article_pret(db, None, nom="Pull non attribué")  # sans compte : jamais traité automatiquement
    assert _suivant(client, jeton_lucas) is None
    photo_soeur = db.scalars(select(PhotoArticle).where(PhotoArticle.article_id == a_soeur.id)).first()
    assert photo_soeur is not None
    assert (
        client.get(f"/api/extension/photos/{photo_soeur.id}", headers=entetes(jeton_lucas)).status_code == 404
    )
    r = client.post(
        f"/api/extension/brouillons/{a_soeur.id}/resultat",
        json={"ok": False, "erreur": "x"},
        headers=entetes(jeton_lucas),
    )
    assert r.status_code == 404
    charge = _suivant(client, jeton_soeur)
    assert charge is not None and charge["article_id"] == a_soeur.id


def test_mauvais_compte_connecte_bloque_tout(client: TestClient, db: Session, journee: None) -> None:
    compte, jeton = creer_compte(db, "Lucas", LUCAS_VINTED)
    article_pret(db, compte)
    heartbeat(client, jeton, SOEUR_VINTED, "soeur")  # la sœur est connectée dans le profil de Lucas
    assert _suivant(client, jeton) is None
    assert _alertes(db, "mauvais_compte")
    heartbeat(client, jeton, LUCAS_VINTED)
    assert _suivant(client, jeton) is not None


def test_sans_identifiant_vinted_attendu_rien_n_est_fait(
    client: TestClient, db: Session, journee: None
) -> None:
    compte, jeton = creer_compte(db, "Lucas", None)
    article_pret(db, compte)
    heartbeat(client, jeton, LUCAS_VINTED)
    assert _suivant(client, jeton) is None


# --- Test de réception 3 : photo de dos manquante --------------------------------------------


def test_article_sans_dos_refuse_avec_notification(client: TestClient, db: Session, journee: None) -> None:
    compte, jeton = creer_compte(db, "Lucas", LUCAS_VINTED)
    a = article_pret(db, compte, types=("devant", "etiquette", "logo", "detail", "detail"))
    assert _suivant(client, jeton) is None
    db.refresh(a)
    assert a.brouillon_statut == "erreur" and a.brouillon_erreur == "Photo manquante : dos."
    alerte = _alertes(db, "brouillon_erreur")
    assert len(alerte) == 1 and "dos" in alerte[0].message
    assert _suivant(client, jeton) is None and len(_alertes(db, "brouillon_erreur")) == 1  # pas de répétition
    # Relance manuelle après ajout de la photo
    db.add(PhotoArticle(article_id=a.id, type="dos", ordre=9, fichier_original=db.scalars(
        select(PhotoArticle.fichier_original).where(PhotoArticle.article_id == a.id)).first() or "", statut="original",
        version_choisie="original"))  # fmt: skip
    db.commit()
    assert client.post(f"/api/articles/{a.id}/brouillon/relancer").status_code == 204
    assert _suivant(client, jeton) is not None


def test_moins_de_5_photos_refuse(db: Session) -> None:
    liste = [PhotoArticle(type=t) for t in ("devant", "dos", "etiquette", "logo")]
    assert brouillons.photos_manquantes(liste) == ["5 photos au total (il y en a 4)"]


# --- Test de réception 4 : quota de 6 brouillons par jour ------------------------------------


def test_septieme_demande_du_jour_non_traitee(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    compte, jeton = creer_compte(db, "Lucas", LUCAS_VINTED)
    for i in range(7):
        article_pret(db, compte, nom=f"T-shirt {i}")
    for i in range(6):
        a_heure(monkeypatch, 9 + i)  # au plus un brouillon toutes les 5 min (+ 0 à 120 s)
        charge = _suivant(client, jeton)
        assert charge is not None, f"demande {i + 1}"
        client.post(
            f"/api/extension/brouillons/{charge['article_id']}/resultat",
            json={"ok": True, "vinted_draft_id": 1000 + i},
            headers=entetes(jeton),
        )
    a_heure(monkeypatch, 16)
    assert _suivant(client, jeton) is None
    assert client.get("/api/automatisation/comptes").json()[0]["brouillons_du_jour"] == 6


def test_aucun_brouillon_la_nuit(client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    compte, jeton = creer_compte(db, "Lucas", LUCAS_VINTED)
    article_pret(db, compte)
    a_heure(monkeypatch, 23, 30)
    assert _suivant(client, jeton) is None
    a_heure(monkeypatch, 7, 59)
    assert _suivant(client, jeton) is None
    a_heure(monkeypatch, 8, 0)
    assert _suivant(client, jeton) is not None


# --- Test de réception 5 : réponse 403 → pause -----------------------------------------------


def test_reponse_403_met_le_compte_en_pause(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    a_heure(monkeypatch, 14)
    compte, jeton = creer_compte(db, "Lucas", LUCAS_VINTED)
    a = article_pret(db, compte)
    article_pret(db, compte, nom="Autre")
    charge = _suivant(client, jeton)
    assert charge is not None
    r = client.post(
        f"/api/extension/brouillons/{a.id}/resultat",
        json={"ok": False, "erreur": "Vinted a répondu 403 (accès refusé).", "arret": True},
        headers=entetes(jeton),
    )
    assert r.status_code == 204
    db.refresh(compte)
    assert compte.pause and "403" in (compte.pause_raison or "")
    assert _alertes(db, "arret")
    assert _suivant(client, jeton) is None  # plus rien tant que Lucas n'a pas repris
    assert client.post(f"/api/automatisation/comptes/{compte.id}/reprendre").json()["pause"] is False
    a_heure(monkeypatch, 14, 10)
    assert _suivant(client, jeton) is not None


def test_arret_signale_hors_tache(client: TestClient, db: Session) -> None:
    compte, jeton = creer_compte(db, "Lucas", LUCAS_VINTED)
    r = client.post(
        "/api/extension/arret", json={"raison": "Captcha Vinted détecté."}, headers=entetes(jeton)
    )
    assert r.json()["pause"] is True


def test_brouillon_reste_en_cours_trop_longtemps(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    compte, jeton = creer_compte(db, "Lucas", LUCAS_VINTED)
    a_heure(monkeypatch, 14)
    a = article_pret(db, compte)
    article_pret(db, compte, nom="Suivant")
    assert _suivant(client, jeton) is not None
    a_heure(monkeypatch, 14, 30)
    assert _suivant(client, jeton) is None  # la tâche interrompue passe en erreur, rien d'autre ce tour-ci
    a_heure(monkeypatch, 14, 40)
    suivant = _suivant(client, jeton)
    db.refresh(a)
    assert a.brouillon_statut == "erreur" and "interrompu" in (a.brouillon_erreur or "")
    assert suivant is not None and suivant["article_id"] != a.id


# --- Fidélité des photos ----------------------------------------------------------------------


def test_couleur_trop_differente_bloque_jusqu_a_validation(
    client: TestClient, db: Session, journee: None
) -> None:
    compte, jeton = creer_compte(db, "Lucas", LUCAS_VINTED)
    a = article_pret(db, compte, couleur_retouche=(200, 60, 60))  # violet devenu rouge
    assert _suivant(client, jeton) is None
    db.refresh(a)
    assert a.couleur_a_verifier and a.brouillon_statut is None
    assert len(_alertes(db, "couleur")) == 1
    douteuses = db.scalars(
        select(PhotoArticle).where(PhotoArticle.article_id == a.id, PhotoArticle.ecart_couleur > 10)
    ).all()
    assert {p.type for p in douteuses} == {"dos", "etiquette", "logo", "detail"}  # « devant » : l'originale
    for p in douteuses:
        assert client.post(f"/api/photos/{p.id}/valider-couleur").status_code == 204
    db.refresh(a)
    assert not a.couleur_a_verifier
    assert _suivant(client, jeton) is not None


def test_delta_e() -> None:
    gris = couleur.lab_moyen_central(jpeg(couleur=(128, 128, 128)))
    assert abs(gris[0] - 53.6) < 1 and abs(gris[1]) < 1 and abs(gris[2]) < 1
    assert couleur.ecart(jpeg(couleur=(128, 128, 128)), jpeg(couleur=(131, 128, 126))) < 3
    assert couleur.ecart(jpeg(couleur=(120, 100, 180)), jpeg(couleur=(200, 60, 60))) > 10


def test_premiere_photo_reelle_desactivable(client: TestClient, db: Session) -> None:
    a = article_pret(db, None)
    devant = db.scalars(
        select(PhotoArticle).where(PhotoArticle.article_id == a.id, PhotoArticle.type == "devant")
    ).one()
    params = get_parametres(db)
    assert brouillons.version_publiee(devant, params) == "original"
    assert (
        client.put("/api/parametres/photos", json={"premiere_photo_reelle": False}).json()[
            "premiere_photo_reelle"
        ]
        is False
    )
    db.refresh(params)
    assert brouillons.version_publiee(devant, params) == "genere"


def test_recadrage_portrait_sans_couper_le_vetement() -> None:
    def taille(contenu: bytes) -> tuple[int, int]:
        return Image.open(io.BytesIO(contenu)).size

    assert taille(brouillons.recadrer(jpeg(1000, 1200))) == (900, 1200)  # légèrement trop large : recadré
    assert taille(brouillons.recadrer(jpeg(1200, 900))) == (1200, 900)  # paysage : on ne coupe pas
    assert taille(brouillons.recadrer(jpeg(600, 800))) == (600, 800)


def test_taille_du_colis_et_prix() -> None:
    assert brouillons.package_size_id("T-shirt") == 1
    assert brouillons.package_size_id("Sweat demi-zip") == 2
    assert brouillons.package_size_id("Veste") == 2
    assert brouillons.package_size_id(None) == 2
    assert brouillons.prix_texte(D("24.00")) == "24" and brouillons.prix_texte(D("24.50")) == "24.5"
    a = Article(nom="x", prix_vente_cible=D("30"))
    brouillons.fixer_prix_initial(a, D("30"))
    assert a.prix_plancher == D("25")  # 24,60 arrondi au-dessus
    brouillons.fixer_prix_initial(a, D("50"))
    assert a.prix_initial == D("30")  # le prix initial ne change plus


def test_compte_inconnu_ou_en_pause(db: Session) -> None:
    c = CompteVinted(nom="x", vinted_user_id=1, pause=True)
    assert not brouillons.compte_pret(c)
    assert db.scalar(select(Article.id)) is None


def test_debrancher_la_boite_garde_le_compte_pilote(client: TestClient, db: Session) -> None:
    compte, _ = creer_compte(db, "Lucas", LUCAS_VINTED)
    compte.imap_serveur, compte.imap_email, compte.imap_mot_de_passe_chiffre = "imap.x", "a@b.c", "chiffre"
    db.commit()
    assert client.delete(f"/api/comptes/{compte.id}").status_code == 204
    db.refresh(compte)
    assert compte.imap_email is None and compte.jeton_extension_hash is not None
    assert client.get("/api/comptes").json()[0]["imap_email"] is None
