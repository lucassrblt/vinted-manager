"""Analyse d'une offre reçue : accepter, contre-proposer ou refuser, avec la marge résultante.

La décision est calculée ici (règle de marge minimale), l'IA ne fait que rédiger la réponse.
"""

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

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


def euros(v: Decimal) -> str:
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
            "accepter", None, f"L'offre respecte la marge minimale ({euros(marge or Decimal(0))} de marge)."
        )
    if montant < mini * SEUIL_REFUS:
        return resultat(
            "refuser",
            None,
            f"Offre trop basse : le minimum pour garder un coefficient de {calculs.nombre_fr(params.coefficient_min)} est {euros(mini)}.",
        )
    # Contre-proposition : à mi-chemin entre l'offre et le prix affiché, jamais sous le plancher.
    milieu = ((montant + (affiche or mini)) / 2).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    propose = max(mini, milieu)
    if affiche is not None:
        propose = min(propose, affiche)
    return resultat(
        "contre_proposer",
        propose,
        f"Contre-proposition à {euros(propose)} (minimum {euros(mini)} pour un coefficient de {calculs.nombre_fr(params.coefficient_min)}).",
    )


# --- Offres reçues sur Vinted, traitées automatiquement par l'assistant (section 8) -----------

CINQUANTE_CENTIMES = Decimal("0.5")


def arrondi_50(v: Decimal, rounding: str = ROUND_HALF_UP) -> Decimal:
    """Montant arrondi aux 50 centimes."""
    return ((v * 2).quantize(Decimal("1"), rounding=rounding) / 2).quantize(Decimal("0.01"))


def plancher_vinted(prix_initial: Decimal, part_pct: Decimal | int | float) -> Decimal:
    """Jamais d'accord sous ce prix : `part_pct` % du prix initial, arrondi aux 50 centimes au-dessus."""
    return arrondi_50(prix_initial * Decimal(str(part_pct)) / 100, ROUND_CEILING)


@dataclass
class DecisionVinted:
    action: str  # accepter | refuser | contre | escalade
    montant: Decimal | None  # contre-offre envoyée (ou montant accepté)
    plancher: Decimal
    explication: str
    renvoi_plancher: bool = False  # contre-offre identique à la précédente, envoyée une seule fois


def decider_vinted(
    offre: Decimal,
    prix_affiche: Decimal,
    prix_initial: Decimal | None,
    dernier_propose: Decimal | None,
    plancher_deja_renvoye: bool,
    seuil_acceptation_pct: float = 90,
    seuil_refus_pct: float = 50,
    plancher_pct: float = 82,
) -> DecisionVinted:
    """Règles déterministes (jamais l'IA) :

    - accepter si l'offre atteint 90 % du prix affiché, ou la dernière contre-offre envoyée ;
    - refuser poliment sous 50 % du prix affiché (offre jugée non sérieuse) ;
    - sinon contre-proposer à mi-chemin entre l'offre et la dernière proposition, arrondi aux 50 centimes,
      jamais sous le plancher (82 % du prix initial) ni au-dessus de la proposition précédente ;
    - déjà au plancher : la même valeur est renvoyée une seule fois, puis Lucas décide (escalade).
    """
    plancher = plancher_vinted(prix_initial or prix_affiche, plancher_pct)
    dernier = dernier_propose if dernier_propose is not None else prix_affiche
    seuil = prix_affiche * Decimal(str(seuil_acceptation_pct)) / 100
    if offre >= seuil or offre >= dernier:
        return DecisionVinted(
            "accepter",
            offre,
            plancher,
            f"Offre de {euros(offre)} acceptée (≥ {euros(seuil)} ou ≥ dernière proposition).",
        )
    if offre < prix_affiche * Decimal(str(seuil_refus_pct)) / 100:
        return DecisionVinted(
            "refuser",
            None,
            plancher,
            f"Offre de {euros(offre)} sous {seuil_refus_pct:g} % du prix affiché : refusée.",
        )
    contre = min(max(plancher, arrondi_50((offre + dernier) / 2)), dernier)
    if contre <= offre:
        return DecisionVinted(
            "accepter",
            offre,
            plancher,
            f"La contre-offre ({euros(contre)}) ne dépasserait pas l'offre : acceptée.",
        )
    if contre >= dernier:
        if plancher_deja_renvoye:
            return DecisionVinted(
                "escalade", None, plancher,
                f"Offre de {euros(offre)} : on est déjà au plancher ({euros(plancher)}), proposé deux fois.",
            )  # fmt: skip
        return DecisionVinted(
            "contre",
            dernier,
            plancher,
            f"Plancher atteint : {euros(dernier)} renvoyé une dernière fois.",
            True,
        )
    return DecisionVinted(
        "contre", contre, plancher, f"Contre-offre à {euros(contre)} (plancher {euros(plancher)})."
    )
