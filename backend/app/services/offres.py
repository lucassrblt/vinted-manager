"""Analyse d'une offre reçue : accepter, contre-proposer ou refuser, avec la marge résultante.

La décision est calculée ici (règle de marge minimale), l'IA ne fait que rédiger la réponse.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.models import Article, Parametres
from app.services import calculs, stats
from app.services.prix_conseille import plancher

# Offre acceptée sans discuter si elle atteint ce pourcentage du prix affiché (et respecte le minimum).
SEUIL_ACCEPTATION = Decimal("0.9")
# En dessous de ce pourcentage du prix plancher, on refuse poliment plutôt que de contre-proposer.
SEUIL_REFUS = Decimal("0.7")


@dataclass
class AnalyseOffre:
    decision: str  # accepter | contre_proposer | refuser
    montant_offre: Decimal
    prix_affiche: Decimal | None
    prix_plancher: Decimal | None
    montant_propose: Decimal | None  # contre-proposition
    marge_si_accepte: Decimal | None
    coefficient_si_accepte: Decimal | None
    marge_proposee: Decimal | None
    explication: str


def _euros(v: Decimal) -> str:
    return f"{v:.2f}".replace(".", ",").replace(",00", "") + " €"


def analyser(article: Article, montant: Decimal, params: Parametres) -> AnalyseOffre:
    affiche = stats.prix_vente(article)
    achat = article.prix_achat_net
    mini = plancher(article, params)
    marge = calculs.marge_nette(montant, achat)
    coeff = calculs.coefficient(montant, achat)

    def resultat(decision: str, propose: Decimal | None, explication: str) -> AnalyseOffre:
        return AnalyseOffre(
            decision=decision,
            montant_offre=montant,
            prix_affiche=affiche,
            prix_plancher=mini,
            montant_propose=propose,
            marge_si_accepte=marge,
            coefficient_si_accepte=coeff.quantize(Decimal("0.01")) if coeff else None,
            marge_proposee=calculs.marge_nette(propose, achat) if propose is not None else None,
            explication=explication,
        )

    if mini is None:
        # Prix d'achat inconnu : on ne peut juger que par rapport au prix affiché.
        if affiche is None or montant >= affiche * SEUIL_ACCEPTATION:
            return resultat("accepter", None, "Prix d'achat inconnu : marge minimale non vérifiable.")
        return resultat(
            "contre_proposer", affiche, "Prix d'achat inconnu : contre-proposition au prix affiché."
        )
    if montant >= mini and (affiche is None or montant >= affiche * SEUIL_ACCEPTATION):
        return resultat(
            "accepter", None, f"L'offre respecte la marge minimale ({_euros(marge or Decimal(0))} de marge)."
        )
    if montant < mini * SEUIL_REFUS:
        return resultat(
            "refuser",
            None,
            f"Offre trop basse : le minimum pour garder un coefficient de {calculs.nombre_fr(params.coefficient_min)} est {_euros(mini)}.",
        )
    # Contre-proposition : à mi-chemin entre l'offre et le prix affiché, jamais sous le plancher.
    milieu = ((montant + (affiche or mini)) / 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    propose = max(mini, milieu)
    if affiche is not None:
        propose = min(propose, affiche)
    return resultat(
        "contre_proposer",
        propose,
        f"Contre-proposition à {_euros(propose)} (minimum {_euros(mini)} pour un coefficient de {calculs.nombre_fr(params.coefficient_min)}).",
    )
