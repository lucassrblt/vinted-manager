"""Règles de classement initiales, installées au premier démarrage (table vide).

Elles sont volontairement larges : le format exact des mails Vinted n'est pas connu. Elles
s'ajustent dans l'app (page Règles) et se vérifient avec les .eml de backend/fixtures/emails/.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import RegleClassement

EXPEDITEURS = ["vinted"]

PRIX = r"(\d{1,4}(?:[.,]\d{1,2})?)\s?€"
TITRE = r"(?:article|annonce|commande)\s*(?:de\s*)?[«\"“]\s*(?P<v>[^»\"”\n]{2,120}?)\s*[»\"”]"
COMMANDE = r"(?:commande|transaction)\s*(?:n°|no|nº|#|numéro)?\s*:?\s*(?P<v>[A-Z0-9][A-Z0-9-]{5,})"
ACHETEUR = r"(?:acheteu(?:r|se)|membre)\s*:?\s*@?(?P<v>[\w.-]{3,40})|(?P<x>[\w.-]{3,40})\s+(?:a acheté|vient d'acheter)"
LIEN_BORDEREAU = r"bordereau|étiquette|etiquette|label|shipping"
DATE_LIMITE = (
    r"(?:avant le|jusqu'au|d'ici le|au plus tard le)\s+(?:\w+\s+)?"
    r"(?P<v>\d{1,2}(?:/\d{1,2}(?:/\d{2,4})?|\s+[a-zéû]+(?:\s+\d{4})?))"
)

REGLES_INITIALES: list[dict] = [
    {
        "nom": "Litige / réclamation",
        "type_cible": "litige",
        "priorite": 10,
        "conditions": {
            "expediteurs": EXPEDITEURS,
            "sujet_contient": [
                "litige",
                "réclamation",
                "problème avec",
                "signalé un problème",
                "remboursement demandé",
                "demande de retour",
            ],
        },
        "extraction": {"titre_article": TITRE, "numero_commande": COMMANDE},
    },
    {
        "nom": "Colis livré",
        "type_cible": "livre",
        "priorite": 20,
        "conditions": {
            "expediteurs": EXPEDITEURS,
            "sujet_contient": ["livré", "a été récupéré", "colis récupéré", "est arrivé"],
        },
        "extraction": {"titre_article": TITRE, "numero_commande": COMMANDE},
    },
    {
        "nom": "Colis expédié",
        "type_cible": "expedie",
        "priorite": 30,
        "conditions": {
            "expediteurs": EXPEDITEURS,
            "sujet_contient": ["expédié", "en route", "en chemin", "déposé", "pris en charge"],
        },
        "extraction": {"titre_article": TITRE, "numero_commande": COMMANDE},
    },
    {
        "nom": "Argent disponible",
        "type_cible": "argent_disponible",
        "priorite": 40,
        "conditions": {
            "expediteurs": EXPEDITEURS,
            "sujet_contient": ["argent", "porte-monnaie", "paiement", "fonds", "virement", "solde"],
        },
        "extraction": {"prix": PRIX, "titre_article": TITRE},
    },
    {
        "nom": "Évaluation reçue",
        "type_cible": "evaluation",
        "priorite": 50,
        "conditions": {
            "expediteurs": EXPEDITEURS,
            "sujet_contient": ["évaluation", "avis", "commentaire", "évalué"],
        },
        "extraction": {"acheteur": ACHETEUR},
    },
    {
        "nom": "Offre reçue",
        "type_cible": "offre",
        "priorite": 60,
        "conditions": {"expediteurs": EXPEDITEURS, "sujet_contient": ["offre", "propose", "proposition"]},
        "extraction": {"montant_offre": PRIX, "titre_article": TITRE, "acheteur": ACHETEUR},
    },
    {
        "nom": "Bordereau d'envoi",
        "type_cible": "bordereau",
        "priorite": 70,
        "conditions": {
            "expediteurs": EXPEDITEURS,
            "sujet_contient": ["bordereau", "étiquette", "envoie ton colis", "à envoyer"],
        },
        "extraction": {
            "titre_article": TITRE,
            "numero_commande": COMMANDE,
            "date_limite": DATE_LIMITE,
            "lien_bordereau": LIEN_BORDEREAU,
        },
    },
    {
        "nom": "Vente",
        "type_cible": "vente",
        "priorite": 80,
        "conditions": {
            "expediteurs": EXPEDITEURS,
            "sujet_contient": ["vendu", "nouvelle commande", "a acheté", "vient d'acheter", "nouvelle vente"],
        },
        "extraction": {
            "prix": PRIX,
            "titre_article": TITRE,
            "numero_commande": COMMANDE,
            "acheteur": ACHETEUR,
            "date_limite": DATE_LIMITE,
            "lien_bordereau": LIEN_BORDEREAU,
        },
    },
    {
        "nom": "Message reçu",
        "type_cible": "message",
        "priorite": 90,
        "conditions": {
            "expediteurs": EXPEDITEURS,
            "sujet_contient": ["message", "t'a écrit", "a écrit", "question"],
        },
        "extraction": {"titre_article": TITRE, "acheteur": ACHETEUR},
    },
]


def installer_regles(db: Session) -> int:
    if (db.scalar(select(func.count(RegleClassement.id))) or 0) > 0:
        return 0
    for r in REGLES_INITIALES:
        db.add(RegleClassement(active=True, **r))
    db.commit()
    return len(REGLES_INITIALES)
