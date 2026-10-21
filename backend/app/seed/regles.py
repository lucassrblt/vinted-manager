"""Règles de classement par défaut, calquées sur les vrais mails Vinted (relevés le 21/10/2026).

Installées au premier démarrage, puis mises à jour quand VERSION_REGLES augmente : les règles par
défaut (reconnues à leur nom) sont réécrites, les règles créées à la main ne sont pas touchées.
Elles s'ajustent dans l'app (page Règles) et se vérifient avec les .eml de backend/fixtures/emails/.

Format des mails Vinted :
- « Ton article s'est vendu ! » : « <acheteur> a acheté <titre> 5,00 € »
- « Bordereau d'envoi Vinted - à utiliser avant le … pour <titre> » : « Article : <titre> »
- « Commande mise à jour pour <titre> » : chaque étape de la commande (expédié, reçu, annulé, retour…)
- « La transaction est finalisée » : « La vente de <titre> a été réalisée avec succès »
- notifications des transporteurs (expéditeur relay.vinted.com), sans titre d'article
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Parametres, RegleClassement

VERSION_REGLES = 3

EXPEDITEURS = ["vinted"]

PRIX = r"(\d{1,4}(?:[.,]\d{1,2})?)\s?€"
TITRE = r"(?:article|annonce|commande)\s*(?:de\s*)?[«\"“]\s*(?P<v>[^»\"”\n]{2,120}?)\s*[»\"”]"
TITRE_COMMANDE_MAJ = r"^Commande mise à jour pour (?P<v>.+?)\s*$"
TITRE_VENTE = r"a acheté\s+(?P<v>[^\n]+?)\s+\d{1,4}(?:[.,]\d{1,2})?\s?€|" + TITRE.replace("(?P<v>", "(?P<x>")
TITRE_BORDEREAU = (
    r"Article\s*:\s*(?P<v>[^\n]+?)\s*(?:\n|Format du colis)|à utiliser avant le .+? pour (?P<x>.+?)\s*$"
)
TITRE_FINALISEE = r"La vente de (?P<v>.+?) a été réalisée"
TITRE_OFFRE = r"^Nouvelle offre pour (?P<v>.+?)\s*$|" + TITRE.replace("(?P<v>", "(?P<x>")
TITRE_MESSAGE = r"^Nouveau message à propos de (?:l'article )?(?P<v>.+?)\s*$|" + TITRE.replace(
    "(?P<v>", "(?P<x>"
)
COMMANDE = r"(?:commande|transaction)\s*(?:n°|no|nº|numéro)?\s*:?\s*#?(?P<v>\d[A-Z0-9-]{5,})"
ACHETEUR = (
    r"(?:acheteu(?:r|se)|membre)\s*:?\s*@?(?P<v>[\w.-]{3,40})"
    r"|(?P<x>[\w.-]{3,40})\s+(?:a acheté|vient d'acheter|te propose d'acheter|vient de t'envoyer|a reçu sa commande)"
    r"|attendons que (?P<y>[\w.-]{3,40}) récupère"
)
LIEN_BORDEREAU = r"bordereau|étiquette|etiquette|label|shipping"
DATE_LIMITE = (
    r"(?:avant le|jusqu'au|d'ici le|au plus tard le)\s*:?\s+(?:\w+\s+)?"
    r"(?P<v>\d{1,2}(?:/\d{1,2}(?:/\d{2,4})?|\s+[a-zéû]+(?:\s+\d{4})?))"
)
SUIVI = {"titre_article": TITRE_COMMANDE_MAJ, "numero_commande": COMMANDE, "acheteur": ACHETEUR}
COMMANDE_MAJ = ["Commande mise à jour"]

REGLES_INITIALES: list[dict] = [
    # --- Bruit : notifications sans action -------------------------------------------------------
    {
        "nom": "Notification transporteur",
        "type_cible": "autre",
        "priorite": 1,
        "conditions": {"expediteurs": ["relay.vinted.com"]},
        "extraction": {},
    },
    {
        "nom": "Achat (côté acheteur) et compte",
        "type_cible": "autre",
        "priorite": 3,
        "conditions": {
            "expediteurs": EXPEDITEURS,
            "sujet_contient": [
                "nous allons nous occuper de ton colis",
                "ton colis arrive aujourd'hui",
                "récupère ton colis",
                "récupérer ton colis",
                "libère de la place dans la consigne",
                "ton numéro de téléphone",
            ],
        },
        "extraction": {},
    },
    {
        "nom": "Article mis en favori",
        "type_cible": "autre",
        "priorite": 2,
        "conditions": {"expediteurs": EXPEDITEURS, "sujet_contient": ["marqué comme favori"]},
        "extraction": {},
    },
    # --- « Commande mise à jour pour <titre> » : une règle par étape ------------------------------
    {
        "nom": "Commande annulée",
        "type_cible": "annulation",
        "priorite": 5,
        "conditions": {
            "expediteurs": EXPEDITEURS,
            "sujet_contient": COMMANDE_MAJ,
            "corps_contient": [
                "transaction a été annulée",
                "commande a été annulée",
                "délai de réservation a expiré",
            ],
        },
        "extraction": SUIVI,
    },
    {
        "nom": "Problème de livraison ou réclamation",
        "type_cible": "litige",
        "priorite": 8,
        "conditions": {
            "expediteurs": EXPEDITEURS,
            "sujet_contient": COMMANDE_MAJ,
            # « signalé un problème concernant » : la mention « sauf si l'acheteur signale un problème »
            # figure dans tous les mails de commande reçue.
            "corps_contient": [
                "pas pu livrer",
                "va t'être retourné",
                "a signalé un problème concernant",
                "refusé ta proposition de remboursement",
            ],
        },
        "extraction": SUIVI,
    },
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
        "nom": "Commande reçue par l'acheteur",
        "type_cible": "livre",
        "priorite": 15,
        "conditions": {
            "expediteurs": EXPEDITEURS,
            "sujet_contient": COMMANDE_MAJ,
            "corps_contient": ["a reçu sa commande", "colis a été livré"],
        },
        "extraction": SUIVI,
    },
    {
        "nom": "Transaction finalisée",
        "type_cible": "livre",
        "priorite": 16,
        "conditions": {"expediteurs": EXPEDITEURS, "sujet_contient": ["transaction est finalisée"]},
        "extraction": {
            "titre_article": TITRE_FINALISEE,
            "numero_commande": COMMANDE,
            "prix": r"Montant de la commande\s*:\s*" + PRIX,
        },
    },
    {
        "nom": "Colis en route",
        "type_cible": "expedie",
        "priorite": 18,
        "conditions": {
            "expediteurs": EXPEDITEURS,
            "sujet_contient": COMMANDE_MAJ,
            "corps_contient": ["en cours d'acheminement", "récupère sa commande"],
        },
        "extraction": SUIVI,
    },
    {
        "nom": "Offre dans la commande",
        "type_cible": "offre",
        "priorite": 19,
        "conditions": {
            "expediteurs": EXPEDITEURS,
            "sujet_contient": COMMANDE_MAJ,
            "corps_contient": ["accepterais-tu de me vendre"],
        },
        "extraction": {"titre_article": TITRE_COMMANDE_MAJ, "montant_offre": r"vendre ceci à\s*" + PRIX},
    },
    {
        "nom": "Autre étape de commande",
        "type_cible": "autre",
        "priorite": 25,
        "conditions": {"expediteurs": EXPEDITEURS, "sujet_contient": COMMANDE_MAJ},
        "extraction": {"titre_article": TITRE_COMMANDE_MAJ},
    },
    # --- Règles par sujet -------------------------------------------------------------------------
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
            "sujet_contient": [
                "argent",
                "porte-monnaie",
                "paiement",
                "fonds",
                "virement",
                "solde",
                "transfert bancaire",
            ],
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
        "extraction": {"acheteur": r"membre\s+(?P<v>[\w.-]{3,40})"},
    },
    {
        "nom": "Offre reçue",
        "type_cible": "offre",
        "priorite": 60,
        "conditions": {"expediteurs": EXPEDITEURS, "sujet_contient": ["offre", "propose", "proposition"]},
        "extraction": {
            "montant_offre": r"Nouvelle offre\s*:\s*" + PRIX + "|" + PRIX,
            "titre_article": TITRE_OFFRE,
            "acheteur": ACHETEUR,
        },
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
            "titre_article": TITRE_BORDEREAU,
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
            "titre_article": TITRE_VENTE,
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
        "extraction": {"titre_article": TITRE_MESSAGE, "acheteur": ACHETEUR},
    },
]


def installer_regles(db: Session) -> int:
    """Installe les règles par défaut (base vide) ou les met à jour quand VERSION_REGLES augmente.
    Renvoie le nombre de règles écrites."""
    params = db.get(Parametres, 1)
    vide = (db.scalar(select(func.count(RegleClassement.id))) or 0) == 0
    if not vide and params is not None and (params.version_regles or 0) >= VERSION_REGLES:
        return 0
    existantes = {r.nom: r for r in db.scalars(select(RegleClassement))}
    for modele in REGLES_INITIALES:
        regle = existantes.get(modele["nom"])
        if regle is None:
            db.add(RegleClassement(active=True, **modele))
        else:
            for cle, valeur in modele.items():
                setattr(regle, cle, valeur)
    if params is None:
        params = Parametres(id=1)
        db.add(params)
    params.version_regles = VERSION_REGLES
    db.commit()
    return len(REGLES_INITIALES)
