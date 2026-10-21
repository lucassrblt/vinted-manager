"""Mails au format réel de Vinted (relevés le 21/10/2026, pseudos et titres modifiés).

Le cycle d'une vente : vendu -> bordereau -> « Commande mise à jour » (en route, en attente de
retrait, reçue) -> « La transaction est finalisée ». Tous ces mails sont reliés par le titre de
l'annonce, le seul repère commun.
"""

from datetime import UTC, datetime
from decimal import Decimal as D

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, EmailVinted, Envoi, Vente
from app.services import traitement
from app.services.email_parser import lire_mail
from app.services.traitement import enregistrer_mail
from tests import mails_synthetiques as ms

TITRE = "Sweat demi-zip Polo Ralph Lauren gris chiné taille M"
PIED = (
    "Cet e-mail t'a été envoyé par Vinted, UAB, Švitrigailos g. 13, LT-03228, Vilnius, Lituanie. "
    "Si tu ne souhaites plus recevoir ces e-mails, tu peux modifier tes préférences."
)


def _id(*parties: object) -> str:
    return f"<{abs(hash(parties))}@vinted.fr>"


def _quand(jour: int, heure: int = 10) -> datetime:
    return datetime(2026, 10, jour, heure, tzinfo=UTC)


def vente(titre: str = TITRE, jour: int = 10, acheteur: str = "jules_75", prix: str = "43,00") -> bytes:
    return ms.mail(
        "Ton article s'est vendu !",
        f"​​Bonjour vendeur,\n{acheteur} a acheté\n{titre}\n{prix} €\n"
        "Nous transférerons le paiement sur ton porte-monnaie Vinted une fois la commande terminée.\n"
        "Expédie cette commande au cours des 5 prochains jours.\n" + PIED,
        message_id=_id("vente", titre, jour),
        date=_quand(jour),
    )


def bordereau(titre: str = TITRE, jour: int = 10) -> bytes:
    return ms.mail(
        f"Bordereau d'envoi Vinted - à utiliser avant le {jour + 7}/10/2026 10 h 00 pour {titre}",
        f"Bonjour vendeur,\nRetrouve ton bordereau d'envoi en pièce jointe de cet e-mail.\n"
        f"Informations d'envoi :\nArticle : {titre}\nFormat du colis : 500.0 g\n"
        f"N° de suivi : XW579574673TS\nÀ envoyer avant le : {jour + 7}/10/2026 10 h 00\n"
        f"N° de transaction : 2259744{jour}81\n" + PIED,
        pdf=ms.pdf_vierge(),
        message_id=_id("bordereau", titre, jour),
        date=_quand(jour, 11),
    )


def commande(titre: str, texte: str, jour: int, cle: str) -> bytes:
    return ms.mail(
        f"Commande mise à jour pour {titre}",
        f"Bonjour,\n{texte}\nAller sur la conversation\n{PIED}",
        message_id=_id(cle, titre, jour),
        date=_quand(jour, 15),
    )


def en_route(titre: str = TITRE, jour: int = 11) -> bytes:
    texte = f"Ton colis est en cours d'acheminement vers l'acheteur ! La livraison est estimée au 14 oct. - 18 oct. pour {titre}."
    return commande(titre, texte, jour, "route")


def recue(titre: str = TITRE, jour: int = 14) -> bytes:
    texte = (
        "jules_75 a reçu sa commande. Le paiement de cette transaction sera automatiquement transféré le "
        "16 oct. 12:10 (sauf si l’acheteur signale un problème avec la commande)."
    )
    return commande(titre, texte, jour, "recue")


def annulee(titre: str = TITRE, jour: int = 12) -> bytes:
    return commande(
        titre, "La transaction a été annulée. L’acheteur va recevoir un remboursement.", jour, "annul"
    )


def finalisee(titre: str = TITRE, jour: int = 16) -> bytes:
    return ms.mail(
        "La transaction est finalisée",
        f"vendeur,\nCette transaction est finalisée.\nLa vente de {titre} a été réalisée avec succès.\n"
        f"N° de Transaction : #22285174200\nDate : {jour}/10/2026 17 h 58\n"
        "Montant de la commande :\n43,00 €\nViré sur ton compte Vinted :\n43,00 €\n" + PIED,
        message_id=_id("fin", titre, jour),
        date=_quand(jour, 18),
    )


def _recevoir(db: Session, *bruts: bytes) -> list[EmailVinted]:
    mails = []
    for brut in bruts:
        email = enregistrer_mail(db, lire_mail(brut))
        assert email is not None
        mails.append(email)
    return mails


def _article(db: Session, nom: str = "Pull demi-zip Ralph Lauren - gris", prix: str = "43") -> Article:
    a = Article(nom=nom, prix_achat_net=D("15"), prix_vente_cible=D(prix), statut="en_ligne")
    db.add(a)
    db.commit()
    return a


def test_extraction_au_format_reel(db: Session, regles: None) -> None:
    v, b, r, f = _recevoir(db, vente(), bordereau(), en_route(), finalisee())
    assert v.type_detecte == "vente" and v.donnees_extraites == {
        "prix": "43.00",
        "titre_article": TITRE,
        "acheteur": "jules_75",
    }
    assert b.type_detecte == "bordereau" and b.donnees_extraites["titre_article"] == TITRE
    assert b.donnees_extraites["numero_commande"] == "22597441081"
    assert r.type_detecte == "expedie" and r.donnees_extraites["titre_article"] == TITRE
    assert f.type_detecte == "livre" and f.donnees_extraites["titre_article"] == TITRE


def test_mention_signale_un_probleme_n_est_pas_un_litige(db: Session, regles: None) -> None:
    [email] = _recevoir(db, recue())
    assert email.type_detecte == "livre"


def test_cycle_complet_relie_par_le_titre(db: Session, regles: None) -> None:
    pull = _article(db, TITRE)  # nom identique : rapprochement automatique
    _recevoir(db, vente(), bordereau(), en_route(), recue(), finalisee())
    db.refresh(pull)
    envoi = db.scalar(select(Envoi))
    assert envoi is not None and envoi.statut == "livre" and envoi.fichier_bordereau
    assert pull.statut == "livre" and pull.titre_annonce == TITRE


def test_confirmer_une_vente_rejoue_ses_mails(client: TestClient, db: Session, regles: None) -> None:
    """Nom de stock différent du titre Vinted : la vente attend une confirmation, ses mails de suivi
    attendent aussi ; à la confirmation, ils sont appliqués dans l'ordre et l'envoi est livré."""
    pull = _article(db)
    _article(db, "Pull demi-zip Ralph Lauren - noir")
    email_vente, *_ = _recevoir(db, vente(), bordereau(), en_route(), recue())
    assert email_vente.statut_traitement == "nouveau" and db.scalar(select(Vente)) is None
    r = client.post("/api/ventes/confirmer", json={"email_id": email_vente.id, "article_id": pull.id})
    assert r.status_code == 200, r.text
    db.expire_all()
    envoi = db.scalar(select(Envoi))
    pull = db.get(Article, pull.id)
    assert envoi is not None and envoi.statut == "livre" and envoi.fichier_bordereau
    assert pull is not None and pull.statut == "livre" and pull.titre_annonce == TITRE
    assert client.get("/api/envois").json()["bordereaux_a_rattacher"] == []


def test_bordereaux_d_une_commande_terminee_masques(client: TestClient, db: Session, regles: None) -> None:
    """Vente hors stock : impossible à rapprocher, mais une fois le colis parti le bordereau n'est plus
    à rattacher."""
    _recevoir(
        db,
        vente("Bonnet Polo Ralph Lauren blanc logo rouge"),
        bordereau("Bonnet Polo Ralph Lauren blanc logo rouge"),
    )
    assert len(client.get("/api/envois").json()["bordereaux_a_rattacher"]) == 1
    _recevoir(db, en_route("Bonnet Polo Ralph Lauren blanc logo rouge"))
    assert client.get("/api/envois").json()["bordereaux_a_rattacher"] == []
    a_rattacher = client.get(
        "/api/emails", params={"statut": "nouveau", "type": "bordereau", "ouverts": True}
    )
    assert a_rattacher.json()["total"] == 0


def test_meme_titre_vendu_deux_fois(db: Session, regles: None) -> None:
    """Deux exemplaires identiques : chaque mail de suivi va à la plus ancienne vente encore ouverte."""
    a1 = _article(db, TITRE)
    _recevoir(db, vente(jour=10), bordereau(jour=10), en_route(jour=11), recue(jour=12))
    a2 = _article(db, TITRE)
    _recevoir(db, vente(jour=13, acheteur="marc_92"), bordereau(jour=13), en_route(jour=14))
    db.refresh(a1)
    db.refresh(a2)
    assert a1.statut == "livre" and a2.statut == "envoye"
    statuts = sorted(db.scalars(select(Envoi.statut)))
    assert statuts == ["depose", "livre"]


def test_meme_titre_departage_par_l_acheteur(db: Session, regles: None) -> None:
    a1 = _article(db, TITRE)
    _recevoir(db, vente(jour=10, acheteur="jules_75"), bordereau(jour=10))
    a2 = _article(db, TITRE)
    _recevoir(db, vente(jour=11, acheteur="marc_92"), bordereau(jour=11))
    # « marc_92 a reçu sa commande » : c'est la deuxième vente, même si la première est encore ouverte
    recu_marc = commande(
        TITRE, "marc_92 a reçu sa commande. Le paiement sera transféré le 16 oct.", 13, "recue"
    )
    _recevoir(db, recu_marc)
    db.refresh(a1)
    db.refresh(a2)
    assert a2.statut == "livre" and a1.statut == "vendu"


def test_commande_annulee(db: Session, regles: None) -> None:
    pull = _article(db, TITRE)
    _recevoir(db, vente(), annulee())
    db.refresh(pull)
    assert pull.statut == "en_ligne" and db.scalar(select(Vente)) is None


def test_vente_annulee_hors_stock_plus_a_confirmer(client: TestClient, db: Session, regles: None) -> None:
    _recevoir(db, vente("Polaire quechua"), annulee("Polaire quechua"))
    assert client.get("/api/ventes/a-confirmer").json() == []


def test_retraitement_apres_mise_a_jour_des_regles(db: Session, regles: None) -> None:
    """Mails reçus avec des règles qui ne les reconnaissaient pas : relus dans l'ordre chronologique."""
    for regle in traitement.regles_actives(db):
        regle.active = False
    db.commit()
    _recevoir(db, vente(), bordereau(), finalisee())
    assert {m.type_detecte for m in db.scalars(select(EmailVinted))} == {None}
    for regle in db.scalars(select(traitement.RegleClassement)):
        regle.active = True
    _article(db, TITRE)
    traitement.retraiter_mails(db)
    envoi = db.scalar(select(Envoi))
    assert envoi is not None and envoi.statut == "livre" and envoi.fichier_bordereau
