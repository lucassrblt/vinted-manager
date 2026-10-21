from enum import StrEnum


class StatutArticle(StrEnum):
    COMMANDE = "commande"
    RECU_A_PUBLIER = "recu_a_publier"
    EN_LIGNE = "en_ligne"
    VENDU = "vendu"
    ENVOYE = "envoye"
    LIVRE = "livre"
    LITIGE = "litige"
    RETOURNE = "retourne"


# Statuts pour lesquels l'article est considéré comme vendu (CA encaissé).
STATUTS_VENDUS = {StatutArticle.VENDU, StatutArticle.ENVOYE, StatutArticle.LIVRE, StatutArticle.LITIGE}
# Statuts pour lesquels l'article a été publié au moins une fois.
STATUTS_PUBLIES = STATUTS_VENDUS | {StatutArticle.EN_LIGNE, StatutArticle.RETOURNE}


class EtatArticle(StrEnum):
    NEUF_ETIQUETTE = "neuf_avec_etiquette"
    NEUF_SANS_ETIQUETTE = "neuf_sans_etiquette"
    TRES_BON = "tres_bon_etat"
    BON = "bon_etat"
    SATISFAISANT = "satisfaisant"


class TypePreuve(StrEnum):
    FACTURE = "facture"
    CAPTURE_COMMANDE = "capture_commande"
    PHOTO_ETIQUETTE = "photo_etiquette"
    CERTIFICAT = "certificat"
    AUTRE = "autre"


class StatutEnvoi(StrEnum):
    A_IMPRIMER = "a_imprimer"
    IMPRIME = "imprime"
    DEPOSE = "depose"
    LIVRE = "livre"


class TypeEmail(StrEnum):
    VENTE = "vente"
    BORDEREAU = "bordereau"
    MESSAGE = "message"
    OFFRE = "offre"
    EXPEDIE = "expedie"
    LIVRE = "livre"
    ARGENT_DISPONIBLE = "argent_disponible"
    EVALUATION = "evaluation"
    LITIGE = "litige"
    AUTRE = "autre"


class StatutTraitementEmail(StrEnum):
    NOUVEAU = "nouveau"
    TRAITE = "traite"
    IGNORE = "ignore"
    A_CLASSER = "a_classer"


class TypeMessage(StrEnum):
    MESSAGE = "message"
    OFFRE = "offre"


class StatutMessage(StrEnum):
    A_TRAITER = "a_traiter"
    REPONDU = "repondu"
    IGNORE = "ignore"
