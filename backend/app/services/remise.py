"""Répartition d'une remise globale au prorata du prix brut de chaque article."""

from decimal import ROUND_DOWN, Decimal

CENTIME = Decimal("0.01")


def repartir_remise(prix_bruts: list[Decimal], remise_globale: Decimal) -> list[Decimal]:
    """Renvoie la remise allouée à chaque article, au centime près.

    La somme des remises allouées est exactement égale à la remise globale : les centimes
    restants après troncature vont aux articles ayant le plus grand reste (méthode du plus fort reste).
    """
    if not prix_bruts:
        return []
    total = sum(prix_bruts, Decimal("0"))
    if remise_globale <= 0 or total <= 0:
        return [Decimal("0.00") for _ in prix_bruts]
    if remise_globale > total:
        raise ValueError("La remise globale dépasse le total brut du batch.")

    exactes = [remise_globale * p / total for p in prix_bruts]
    tronquees = [e.quantize(CENTIME, rounding=ROUND_DOWN) for e in exactes]
    reste_centimes = int(((remise_globale - sum(tronquees, Decimal("0"))) / CENTIME).to_integral_value())
    ordre = sorted(
        range(len(exactes)), key=lambda i: (exactes[i] - tronquees[i], prix_bruts[i]), reverse=True
    )
    for i in ordre[:reste_centimes]:
        tronquees[i] += CENTIME
    return tronquees
