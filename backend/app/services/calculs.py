"""Calculs métier, identiques aux formules de l'Excel « Suivi revente ».

Fonctions pures : aucune dépendance à la base, testées dans tests/test_calculs.py.
"""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum

DEUX = Decimal("2")
QUATRE = Decimal("4")
CENTIME = Decimal("0.01")


class Indicateur(StrEnum):
    SOUS_OBJECTIF = "Sous l'objectif"
    OK = "OK"
    AU_DESSUS = "Au-dessus"


def arrondi_euros(valeur: Decimal) -> Decimal:
    return valeur.quantize(CENTIME, rounding=ROUND_HALF_UP)


def marge_nette(prix_vente: Decimal | None, prix_achat_net: Decimal | None) -> Decimal | None:
    if prix_vente is None or prix_achat_net is None:
        return None
    return prix_vente - prix_achat_net


def marge_pct(prix_vente: Decimal | None, prix_achat_net: Decimal | None) -> Decimal | None:
    marge = marge_nette(prix_vente, prix_achat_net)
    if marge is None or not prix_achat_net:
        return None
    return marge / prix_achat_net


def coefficient(prix_vente: Decimal | None, prix_achat_net: Decimal | None) -> Decimal | None:
    if prix_vente is None or not prix_achat_net:
        return None
    return prix_vente / prix_achat_net


def indicateur(
    coeff: Decimal | None, coeff_min: Decimal = DEUX, coeff_max: Decimal = QUATRE
) -> Indicateur | None:
    if coeff is None:
        return None
    if coeff < coeff_min:
        return Indicateur.SOUS_OBJECTIF
    if coeff > coeff_max:
        return Indicateur.AU_DESSUS
    return Indicateur.OK


def delai_vente_heures(date_publication: datetime | None, date_vente: datetime | None) -> float | None:
    if date_publication is None or date_vente is None:
        return None
    return (date_vente - date_publication).total_seconds() / 3600


def delai_vente_jours(date_publication: datetime | None, date_vente: datetime | None) -> float | None:
    heures = delai_vente_heures(date_publication, date_vente)
    return None if heures is None else heures / 24


def sell_through(nb_vendus: int, nb_publies: int) -> Decimal | None:
    if nb_publies == 0:
        return None
    return Decimal(nb_vendus) / Decimal(nb_publies)


def prix_achat_net(prix_brut: Decimal | None, remise: Decimal | None) -> Decimal | None:
    if prix_brut is None:
        return None
    return arrondi_euros(prix_brut - (remise or Decimal("0")))
