"""Prix conseillé, calculé à partir des ventes passées (jamais par l'IA).

1. ventes de même marque et même catégorie, sinon même catégorie, sinon même marque ;
2. médiane, fourchette basse/haute et délai moyen ;
3. vérification du coefficient par rapport à l'objectif ;
4. arrondi : à l'euro sous le seuil, au multiple du pas au-dessus.
"""

import statistics
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from app.models import Article, Parametres
from app.services import calculs, stats
from app.services.marques import normaliser

MIN_VENTES = 3
# Sans historique suffisant : un peu au-dessus de l'objectif minimal.
MARGE_COEFFICIENT_ESTIMATION = Decimal("0.5")
NIVEAUX = (
    ("marque+categorie", "même marque et même catégorie"),
    ("categorie", "même catégorie"),
    ("marque", "même marque"),
)


@dataclass
class PrixConseille:
    prix: Decimal | None
    estimation: bool
    base: str | None
    nb_ventes: int
    mediane: Decimal | None
    fourchette_basse: Decimal | None
    fourchette_haute: Decimal | None
    delai_moyen_jours: float | None
    coefficient: Decimal | None
    sous_objectif_releve: bool
    raisonnement: str


def arrondir(prix: Decimal, params: Parametres) -> Decimal:
    if prix < params.arrondi_seuil:
        return prix.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    pas = params.arrondi_pas
    return ((prix / pas).quantize(Decimal("1"), rounding=ROUND_HALF_UP) * pas).quantize(Decimal("1"))


def plancher(article: Article, params: Parametres) -> Decimal | None:
    """Plus petit prix arrondi qui respecte le coefficient minimal."""
    if not article.prix_achat_net:
        return None
    brut = (article.prix_achat_net * params.coefficient_min).quantize(Decimal("1"), rounding=ROUND_CEILING)
    prix = arrondir(brut, params)
    while prix < brut:  # l'arrondi au multiple de 5 peut descendre sous le minimum
        prix += params.arrondi_pas if prix >= params.arrondi_seuil else Decimal("1")
    return prix


def _jours(v: float) -> str:
    """Une décimale, à la française, sans « ,0 » inutile : 2,3 ou 2."""
    texte = f"{v:.1f}"
    return (texte[:-2] if texte.endswith(".0") else texte).replace(".", ",")


def _euros(v: Decimal) -> str:
    return f"{v:.2f}".replace(".", ",").replace(",00", "") + " €"


def _meme(a: str | None, b: str | None) -> bool:
    return bool(a and b and normaliser(a) == normaliser(b))


def calculer(article: Article, vendus: list[Article], params: Parametres) -> PrixConseille:
    historique = [v for v in vendus if v.id != article.id and stats.prix_vente(v) is not None]
    filtres = {
        "marque+categorie": lambda v: (
            _meme(v.marque, article.marque) and _meme(v.categorie, article.categorie)
        ),
        "categorie": lambda v: _meme(v.categorie, article.categorie),
        "marque": lambda v: _meme(v.marque, article.marque),
    }
    for base, libelle in NIVEAUX:
        similaires = [v for v in historique if filtres[base](v)]
        if len(similaires) >= MIN_VENTES:
            return _depuis_historique(article, similaires, base, libelle, params)
    return _estimation(article, params)


def _depuis_historique(
    article: Article, similaires: list[Article], base: str, libelle: str, params: Parametres
) -> PrixConseille:
    prix = sorted(stats.prix_vente(v) or Decimal("0") for v in similaires)
    mediane = Decimal(str(statistics.median(prix))).quantize(Decimal("0.01"))
    if len(prix) >= 4:
        q = statistics.quantiles(prix, n=4)
        basse, haute = Decimal(str(q[0])), Decimal(str(q[2]))
    else:
        basse, haute = prix[0], prix[-1]
    delais = [
        d
        for v in similaires
        if (d := calculs.delai_vente_jours(v.date_publication, v.date_vente)) is not None
    ]
    delai = statistics.fmean(delais) if delais else None
    conseille = arrondir(mediane, params)
    releve = False
    mini = plancher(article, params)
    if mini is not None and conseille < mini:
        conseille, releve = mini, True
    coeff = calculs.coefficient(conseille, article.prix_achat_net)
    morceaux = [f"{len(similaires)} ventes similaires ({libelle})", f"médiane {_euros(mediane)}"]
    if delai is not None:
        morceaux.append(f"vendues en {_jours(delai)} jour{'s' if delai >= 2 else ''} en moyenne")
    if coeff is not None:
        morceaux.append(f"coefficient {_jours(float(coeff))}")
    raisonnement = ", ".join(morceaux)
    if releve:
        raisonnement += f". Prix relevé à {_euros(conseille)} pour respecter le coefficient minimal ({calculs.nombre_fr(params.coefficient_min)})"
    return PrixConseille(
        prix=conseille,
        estimation=False,
        base=base,
        nb_ventes=len(similaires),
        mediane=mediane,
        fourchette_basse=basse.quantize(Decimal("0.01")),
        fourchette_haute=haute.quantize(Decimal("0.01")),
        delai_moyen_jours=delai,
        coefficient=coeff.quantize(Decimal("0.01")) if coeff else None,
        sous_objectif_releve=releve,
        raisonnement=raisonnement,
    )


def _estimation(article: Article, params: Parametres) -> PrixConseille:
    if not article.prix_achat_net:
        return PrixConseille(None, True, None, 0, None, None, None, None, None, False,
                             "Pas assez de ventes similaires et pas de prix d'achat : impossible d'estimer un prix.")  # fmt: skip
    coeff_cible = params.coefficient_min + MARGE_COEFFICIENT_ESTIMATION
    prix = arrondir(article.prix_achat_net * coeff_cible, params)
    coeff = calculs.coefficient(prix, article.prix_achat_net)
    return PrixConseille(
        prix=prix,
        estimation=True,
        base=None,
        nb_ventes=0,
        mediane=None,
        fourchette_basse=None,
        fourchette_haute=None,
        delai_moyen_jours=None,
        coefficient=coeff.quantize(Decimal("0.01")) if coeff else None,
        sous_objectif_releve=False,
        raisonnement=(
            f"Estimation : moins de {MIN_VENTES} ventes similaires dans ton historique. "
            f"Prix basé sur un coefficient de {calculs.nombre_fr(coeff_cible)} appliqué au prix d'achat ({_euros(article.prix_achat_net)})."
        ),
    )


def nouveau_prix_article_lent(
    article: Article, conseille: PrixConseille, params: Parametres
) -> Decimal | None:
    """Article qui traîne : -10 % (ou le prix conseillé s'il est plus bas), sans passer sous le plancher."""
    actuel = stats.prix_vente(article)
    if actuel is None:
        return conseille.prix
    cible = arrondir(actuel * Decimal("0.9"), params)
    if conseille.prix is not None and not conseille.estimation:
        cible = min(cible, conseille.prix)
    mini = plancher(article, params)
    if mini is not None:
        cible = max(cible, mini)
    return cible if cible < actuel else None
