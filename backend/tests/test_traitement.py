from decimal import Decimal as D

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, EmailVinted, Envoi, HistoriqueStatut, Message, Vente
from app.services.email_parser import lire_mail
from app.services.traitement import enregistrer_mail
from tests import mails_synthetiques as ms


def _article(db: Session, nom: str, prix: str = "45", statut: str = "en_ligne") -> Article:
    a = Article(nom=nom, prix_achat_net=D("16.67"), prix_vente_cible=D(prix), statut=statut)
    db.add(a)
    db.commit()
    return a


def _recevoir(db: Session, brut: bytes) -> EmailVinted:
    email = enregistrer_mail(db, lire_mail(brut))
    assert email is not None
    return email


def test_vente_rapprochee_automatiquement(db: Session, regles: None) -> None:
    pull = _article(db, "Pull demi-zip polaire Ralph Lauren - Noir")
    _article(db, "Bonnet Ralph Lauren - Blanc", "16")
    email = _recevoir(db, ms.VENTE)
    db.refresh(pull)
    assert email.statut_traitement == "traite" and email.article_id == pull.id
    assert pull.statut == "vendu" and pull.prix_vente_reel == D("45.00")
    assert pull.date_vente == ms.DATE  # date et heure exactes du mail
    vente = db.scalar(select(Vente))
    assert vente is not None and vente.auto_rapproche and vente.acheteur == "claire_75"
    envoi = db.scalar(select(Envoi))
    assert envoi is not None and envoi.statut == "a_imprimer"
    assert envoi.date_limite_envoi is not None and envoi.date_limite_envoi.date().isoformat() == "2026-10-27"
    assert envoi.lien_bordereau == "https://www.vinted.fr/shipping/label/123"


def test_vente_ambigue_a_confirmer(client: TestClient, db: Session, regles: None) -> None:
    a = _article(db, "Pull demi-zip polaire Ralph Lauren - Noir")
    _article(db, "Pull demi-zip polaire Ralph Lauren - Noir")  # doublon : impossible de choisir seul
    email = _recevoir(db, ms.VENTE)
    assert email.statut_traitement == "nouveau" and db.scalar(select(Vente)) is None

    liste = client.get("/api/ventes/a-confirmer").json()
    assert len(liste) == 1 and len(liste[0]["candidats"]) == 2
    r = client.post("/api/ventes/confirmer", json={"email_id": email.id, "article_id": a.id})
    assert r.status_code == 200, r.text
    assert client.get("/api/ventes/a-confirmer").json() == []
    assert (
        client.post("/api/ventes/confirmer", json={"email_id": email.id, "article_id": a.id}).status_code
        == 409
    )
    vente = client.get("/api/ventes").json()[0]
    assert vente["auto_rapproche"] is False and vente["article"]["id"] == a.id


def test_annulation_rapprochement(client: TestClient, db: Session, regles: None) -> None:
    pull = _article(db, "Pull demi-zip polaire Ralph Lauren - Noir")
    _recevoir(db, ms.VENTE)
    vente = db.scalar(select(Vente))
    assert vente is not None
    assert client.post(f"/api/ventes/{vente.id}/annuler").status_code == 204
    db.expire_all()
    pull = db.get(Article, pull.id)
    assert pull is not None and pull.statut == "en_ligne" and pull.date_vente is None
    assert db.scalar(select(Envoi)) is None
    assert len(client.get("/api/ventes/a-confirmer").json()) == 1  # revient à confirmer


def test_cycle_complet_bordereau_expedition_livraison(client: TestClient, db: Session, regles: None) -> None:
    pull = _article(db, "Pull demi-zip polaire Ralph Lauren - Noir")
    _recevoir(db, ms.VENTE)
    bordereau = _recevoir(db, ms.BORDEREAU)
    assert bordereau.statut_traitement == "traite"
    envoi = db.scalar(select(Envoi))
    assert envoi is not None and envoi.fichier_bordereau
    assert client.get(f"/api/envois/{envoi.id}/bordereau").content.startswith(b"%PDF")

    _recevoir(db, ms.EXPEDIE)
    db.refresh(pull)
    db.refresh(envoi)
    assert envoi.statut == "depose" and pull.statut == "envoye"

    _recevoir(db, ms.LIVRE)
    db.refresh(pull)
    db.refresh(envoi)
    assert envoi.statut == "livre" and pull.statut == "livre"
    statuts = [h.nouveau_statut for h in db.scalars(select(HistoriqueStatut).order_by(HistoriqueStatut.id))]
    assert statuts[-3:] == ["vendu", "envoye", "livre"]


def test_litige(client: TestClient, db: Session, regles: None) -> None:
    pull = _article(db, "Pull demi-zip polaire Ralph Lauren - Noir")
    _recevoir(db, ms.VENTE)
    _recevoir(db, ms.LITIGE)
    db.refresh(pull)
    assert pull.statut == "litige" and pull.litige
    assert client.get("/api/alertes").json()["litiges"] == [{"id": pull.id, "nom": pull.nom}]


def test_offre_et_message_creent_un_message(db: Session, regles: None) -> None:
    tibet = _article(db, "Pull demi-zip polaire Ralph Lauren - Tibet", "40")
    bonnet = _article(db, "Bonnet Ralph Lauren - Blanc", "16")
    _recevoir(db, ms.OFFRE)
    _recevoir(db, ms.MESSAGE)
    messages = {m.type: m for m in db.scalars(select(Message))}
    assert messages["offre"].article_id == tibet.id and messages["offre"].montant_offre == D("35.00")
    assert messages["message"].article_id == bonnet.id and messages["message"].statut == "a_traiter"


def test_dedoublonnage_message_id(db: Session, regles: None) -> None:
    assert enregistrer_mail(db, lire_mail(ms.ARGENT)) is not None
    assert enregistrer_mail(db, lire_mail(ms.ARGENT)) is None


def test_mail_non_classe_puis_classement_manuel(client: TestClient, db: Session, regles: None) -> None:
    email = _recevoir(db, ms.INCONNU)
    assert email.statut_traitement == "a_classer"
    r = client.post(f"/api/emails/{email.id}/classer", json={"type": "evaluation"})
    assert r.json()["type_detecte"] == "evaluation" and r.json()["statut_traitement"] == "traite"
    r = client.post(f"/api/emails/{email.id}/classer", json={"type": None})
    assert r.json()["statut_traitement"] == "ignore"


def test_bordereau_rattache_a_la_main(client: TestClient, db: Session, regles: None) -> None:
    a1 = _article(db, "Pull demi-zip polaire Ralph Lauren - Noir")
    a2 = _article(db, "Bonnet Ralph Lauren - Blanc", "16")
    for a in (a1, a2):  # deux ventes confirmées sans bordereau
        e = _recevoir(
            db, ms.mail("Ton article a été vendu !", f"Article « {a.nom} ».", message_id=f"<v{a.id}@x>")
        )
        if e.statut_traitement != "traite":
            client.post("/api/ventes/confirmer", json={"email_id": e.id, "article_id": a.id})
    brut = ms.mail(
        "Ton bordereau d'envoi est prêt", "Voici ton bordereau.", pdf=ms.pdf_vierge(), message_id="<b@x>"
    )
    email = _recevoir(db, brut)
    assert email.statut_traitement == "nouveau"
    envois = client.get("/api/envois").json()
    assert len(envois["bordereaux_a_rattacher"]) == 1
    r = client.post(f"/api/emails/{email.id}/rattacher", json={"article_id": a2.id})
    assert r.status_code == 200, r.text
    envoi = next(e for e in client.get("/api/envois").json()["envois"] if e["article"]["id"] == a2.id)
    assert envoi["a_bordereau_pdf"]


def test_rapprochement_distingue_les_couleurs(db: Session, regles: None) -> None:
    """Même marque, même prix, couleur différente : le bon article doit être choisi seul."""
    bleu = _article(db, "Bonnet Ralph Lauren - bleu marine", "16")
    _article(db, "Bonnet Ralph Lauren - Blanc", "16")
    _article(db, "Bonnet Ralph Lauren - Noir", "16")
    brut = ms.mail(
        "Ton article a été vendu !",
        "Article « Bonnet Ralph Lauren bleu marine ».\nPrix : 16,00 €",
        message_id="<c@x>",
    )
    email = _recevoir(db, brut)
    assert email.statut_traitement == "traite" and email.article_id == bleu.id


def test_message_sur_article_en_double(db: Session, regles: None) -> None:
    """Exemplaires identiques en ligne + même article déjà vendu : le message va à un exemplaire en ligne."""
    en_ligne = [_article(db, "Bonnet Ralph Lauren - Blanc", "16") for _ in range(2)]
    _article(db, "Bonnet Ralph Lauren - Blanc", "16", statut="vendu")
    _recevoir(db, ms.MESSAGE)
    message = db.scalar(select(Message))
    assert message is not None and message.article_id == en_ligne[0].id


def _vendu_importe(db: Session, nom: str, prix_reel: str = "45") -> Article:
    """Article vendu venu de l'Excel : date de vente estimée, aucune vente enregistrée."""
    from datetime import UTC, datetime

    from app.services.statuts import changer_statut

    a = Article(nom=nom, prix_achat_net=D("16.67"), prix_vente_reel=D(prix_reel), statut="commande")
    db.add(a)
    changer_statut(
        db, a, "vendu", quand=datetime(2026, 10, 5, 12, tzinfo=UTC), commentaire="Import Excel (date estimée)"
    )
    db.commit()
    return a


def test_historique_corrige_la_date_d_une_vente_importee(
    client: TestClient, db: Session, regles: None
) -> None:
    pull = _vendu_importe(db, "Pull demi-zip polaire Ralph Lauren - Noir")
    autre = _article(db, "Bonnet Ralph Lauren - Blanc", "16")
    email = _recevoir(db, ms.VENTE)
    db.refresh(pull)
    db.refresh(autre)
    assert email.statut_traitement == "traite" and email.article_id == pull.id
    assert pull.statut == "vendu" and pull.date_vente == ms.DATE and autre.statut == "en_ligne"
    vente = db.scalar(select(Vente))
    assert vente is not None and vente.acheteur == "claire_75" and vente.prix == D("45.00")
    passage = db.scalar(select(HistoriqueStatut).where(HistoriqueStatut.nouveau_statut == "vendu"))
    assert passage is not None and passage.date == ms.DATE and "corrigée" in (passage.commentaire or "")
    # Annuler : l'article reste vendu avec sa date estimée d'origine
    assert client.post(f"/api/ventes/{vente.id}/annuler").status_code == 204
    db.expire_all()
    pull = db.get(Article, pull.id)
    assert pull is not None and pull.statut == "vendu" and pull.date_vente is not None
    assert pull.date_vente.day == 5
    a_confirmer = client.get("/api/ventes/a-confirmer").json()
    assert a_confirmer[0]["candidats"][0]["deja_vendu"] is True
    # Confirmation à la main sur l'article importé : acceptée
    r = client.post("/api/ventes/confirmer", json={"email_id": email.id, "article_id": pull.id})
    assert r.status_code == 200, r.text
    # Il a maintenant une vente : un autre mail ne peut plus lui être rattaché
    assert (
        client.post("/api/ventes/confirmer", json={"email_id": email.id, "article_id": pull.id}).status_code
        == 409
    )


def test_vente_importee_n_est_pas_volee_par_un_article_en_ligne(db: Session, regles: None) -> None:
    """Le même modèle vendu (import) et un exemplaire encore en ligne : à confirmer, jamais au hasard."""
    _vendu_importe(db, "Pull demi-zip polaire Ralph Lauren - Noir")
    en_ligne = _article(db, "Pull demi-zip polaire Ralph Lauren - Noir")
    email = _recevoir(db, ms.VENTE)
    db.refresh(en_ligne)
    assert email.statut_traitement == "nouveau" and en_ligne.statut == "en_ligne"


def test_article_achete_apres_la_vente_exclu(db: Session, regles: None) -> None:
    from datetime import date

    pull = _article(db, "Pull demi-zip polaire Ralph Lauren - Noir")
    pull.date_achat = date(2026, 10, 25)  # après le mail (20/10)
    db.commit()
    email = _recevoir(db, ms.VENTE)
    assert email.statut_traitement == "nouveau" and db.scalar(select(Vente)) is None
