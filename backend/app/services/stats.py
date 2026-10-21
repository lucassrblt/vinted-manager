"""Agrégats pour les pages Compta, Batches et Sourcing.

Les volumes sont faibles (quelques centaines d'articles) : on charge les articles et on agrège
en Python, avec les fonctions de `calculs` (une seule définition de chaque formule).
"""

import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.config import get_settings
from app.models import Article, Batch, Parametres, PisteSourcing
from app.models.enums import STATUTS_PUBLIES, STATUTS_VENDUS, StatutArticle
from app.services import calculs, marques

ZERO = Decimal("0")


def tz() -> ZoneInfo:
    return ZoneInfo(get_settings().timezone)


def est_vendu(a: Article) -> bool:
    return a.statut in STATUTS_VENDUS


def est_publie(a: Article) -> bool:
    return a.statut in STATUTS_PUBLIES


def prix_vente(a: Article) -> Decimal | None:
    return a.prix_vente_reel if a.prix_vente_reel is not None else a.prix_vente_cible


def cout(a: Article) -> Decimal:
    return a.prix_achat_net or ZERO


def jour_local(dt: datetime) -> date:
    return dt.astimezone(tz()).date()


def tous_les_articles(db: Session) -> list[Article]:
    return list(db.scalars(select(Article).options(selectinload(Article.batch))))


# --- Compta ----------------------------------------------------------------------------------


class Kpis(BaseModel):
    ca_encaisse: Decimal
    nb_ventes: int
    ventes_sans_date: int
    marge_realisee: Decimal
    cotisations_estimees: Decimal
    marge_apres_cotisations: Decimal
    delai_moyen_heures: float | None
    # Instantané du stock (non filtré par période)
    total_investi: Decimal
    valeur_stock: Decimal
    marge_globale: Decimal
    marge_globale_apres_cotisations: Decimal
    coefficient_global: Decimal | None
    sell_through: Decimal | None
    nb_total: int
    nb_vendus: int
    nb_en_stock: int
    nb_recus: int
    nb_publies: int
    nb_a_publier: int
    taux_cotisations: Decimal


def dans_periode(a: Article, du: date | None, au: date | None) -> bool:
    """Vente comprise dans [du, au] (dates locales). Sans filtre, toutes les ventes comptent."""
    if du is None and au is None:
        return True
    if a.date_vente is None:
        return False
    j = jour_local(a.date_vente)
    return (du is None or j >= du) and (au is None or j <= au)


def kpis(articles: list[Article], params: Parametres, du: date | None, au: date | None) -> Kpis:
    vendus_tous = [a for a in articles if est_vendu(a)]
    vendus = [a for a in vendus_tous if dans_periode(a, du, au)]
    ca = sum((prix_vente(a) or ZERO for a in vendus), ZERO)
    marge_realisee = sum((calculs.marge_nette(prix_vente(a) or ZERO, cout(a)) or ZERO for a in vendus), ZERO)
    taux = params.taux_cotisations
    cotisations = calculs.arrondi_euros(ca * taux)
    delais = [
        d for a in vendus if (d := calculs.delai_vente_heures(a.date_publication, a.date_vente)) is not None
    ]

    investi = sum((cout(a) for a in articles), ZERO)
    stock = [a for a in articles if not est_vendu(a) and a.statut != StatutArticle.RETOURNE]
    valeur_stock = sum((cout(a) for a in stock), ZERO)
    ca_total = sum((prix_vente(a) or ZERO for a in vendus_tous), ZERO)
    marge_globale = ca_total - investi
    publies = [a for a in articles if est_publie(a)]
    return Kpis(
        ca_encaisse=ca,
        nb_ventes=len(vendus),
        ventes_sans_date=sum(1 for a in vendus_tous if a.date_vente is None) if (du or au) else 0,
        marge_realisee=marge_realisee,
        cotisations_estimees=cotisations,
        marge_apres_cotisations=marge_realisee - cotisations,
        delai_moyen_heures=statistics.fmean(delais) if delais else None,
        total_investi=investi,
        valeur_stock=valeur_stock,
        marge_globale=marge_globale,
        marge_globale_apres_cotisations=marge_globale - calculs.arrondi_euros(ca_total * taux),
        coefficient_global=calculs.coefficient(ca_total, investi),
        sell_through=calculs.sell_through(len(vendus_tous), len(publies)),
        nb_total=len(articles),
        nb_vendus=len(vendus_tous),
        nb_en_stock=len(stock),
        nb_recus=sum(1 for a in articles if a.statut != StatutArticle.COMMANDE),
        nb_publies=len(publies),
        nb_a_publier=sum(1 for a in articles if a.statut == StatutArticle.RECU_A_PUBLIER),
        taux_cotisations=taux,
    )


class PointSerie(BaseModel):
    periode: str  # "2026-10" ou "2026-S41" (semaine ISO)
    debut: date
    ca: Decimal
    marge: Decimal
    nb_ventes: int


def debut_periode(j: date, granularite: str) -> date:
    if granularite == "mois":
        return j.replace(day=1)
    return j - timedelta(days=j.weekday())


def libelle_periode(debut: date, granularite: str) -> str:
    if granularite == "mois":
        return f"{debut.year}-{debut.month:02d}"
    iso = debut.isocalendar()
    return f"{iso.year}-S{iso.week:02d}"


def series(articles: list[Article], granularite: str, du: date | None, au: date | None) -> list[PointSerie]:
    points: dict[date, PointSerie] = {}
    for a in articles:
        if not est_vendu(a) or a.date_vente is None or not dans_periode(a, du, au):
            continue
        debut = debut_periode(jour_local(a.date_vente), granularite)
        p = points.setdefault(
            debut,
            PointSerie(
                periode=libelle_periode(debut, granularite), debut=debut, ca=ZERO, marge=ZERO, nb_ventes=0
            ),
        )
        pv = prix_vente(a) or ZERO
        p.ca += pv
        p.marge += pv - cout(a)
        p.nb_ventes += 1
    return [points[k] for k in sorted(points)]


class LigneRepartition(BaseModel):
    cle: str
    nb_ventes: int
    ca: Decimal
    marge: Decimal
    delai_moyen_heures: float | None


def repartition(
    articles: list[Article], champ: str, du: date | None, au: date | None
) -> list[LigneRepartition]:
    groupes: dict[str, list[Article]] = defaultdict(list)
    for a in articles:
        if est_vendu(a) and dans_periode(a, du, au):
            groupes[getattr(a, champ) or "Non renseigné"].append(a)
    lignes = []
    for cle, membres in groupes.items():
        delais = [
            d
            for a in membres
            if (d := calculs.delai_vente_heures(a.date_publication, a.date_vente)) is not None
        ]
        lignes.append(
            LigneRepartition(
                cle=cle,
                nb_ventes=len(membres),
                ca=sum((prix_vente(a) or ZERO for a in membres), ZERO),
                marge=sum(((prix_vente(a) or ZERO) - cout(a) for a in membres), ZERO),
                delai_moyen_heures=statistics.fmean(delais) if delais else None,
            )
        )
    return sorted(lignes, key=lambda x: x.ca, reverse=True)


def lignes_urssaf(articles: list[Article], annee: int, mois: int) -> list[tuple[date, str, Decimal]]:
    lignes = []
    for a in articles:
        if est_vendu(a) and a.date_vente is not None:
            j = jour_local(a.date_vente)
            if j.year == annee and j.month == mois:
                lignes.append((j, a.nom, prix_vente(a) or ZERO))
    return sorted(lignes)


# --- Batches ---------------------------------------------------------------------------------


def stats_batch(batch: Batch, articles: list[Article]) -> dict[str, object]:
    vendus = [a for a in articles if est_vendu(a)]
    publies = [a for a in articles if est_publie(a)]
    ca = sum((prix_vente(a) or ZERO for a in vendus), ZERO)
    cout_vendus = sum((cout(a) for a in vendus), ZERO)
    delais = [
        d for a in vendus if (d := calculs.delai_vente_heures(a.date_publication, a.date_vente)) is not None
    ]
    return {
        "id": batch.id,
        "nom": batch.nom,
        "fournisseur": batch.fournisseur,
        "date_commande": batch.date_commande,
        "total_paye": batch.total_paye,
        "remise_globale": batch.remise_globale,
        "notes": batch.notes,
        "nb_articles": len(articles),
        "nb_publies": len(publies),
        "nb_vendus": len(vendus),
        "sell_through": calculs.sell_through(len(vendus), len(publies)),
        "ca": ca,
        "marge_realisee": ca - cout_vendus,
        "coefficient_ventes": calculs.coefficient(ca, cout_vendus),
        "delai_moyen_heures": statistics.fmean(delais) if delais else None,
        "valeur_stock_restant": sum((cout(a) for a in articles if not est_vendu(a)), ZERO),
        "investi": sum((cout(a) for a in articles), ZERO),
    }


# --- Sourcing --------------------------------------------------------------------------------


class Perf(BaseModel):
    nb_ventes: int = 0
    prix_moyen: Decimal | None = None
    delai_moyen_jours: float | None = None
    coefficient_moyen: Decimal | None = None
    base: str | None = None


def _perf(membres: list[Article], base: str) -> Perf:
    prix = [prix_vente(a) or ZERO for a in membres]
    coeffs = [c for a in membres if (c := calculs.coefficient(prix_vente(a), a.prix_achat_net)) is not None]
    delais = [
        d for a in membres if (d := calculs.delai_vente_jours(a.date_publication, a.date_vente)) is not None
    ]
    n = Decimal(len(membres))
    return Perf(
        nb_ventes=len(membres),
        prix_moyen=calculs.arrondi_euros(sum(prix, ZERO) / n),
        delai_moyen_jours=statistics.fmean(delais) if delais else None,
        coefficient_moyen=(sum(coeffs, ZERO) / Decimal(len(coeffs))).quantize(Decimal("0.01"))
        if coeffs
        else None,
        base=base,
    )


def perf_historique(vendus: list[Article], marque: str | None, categorie: str | None) -> Perf:
    """Performances réelles : même marque + catégorie, sinon même marque, sinon même catégorie."""
    m = marques.normaliser(marque) if marque else None
    c = marques.normaliser(categorie) if categorie else None

    def meme_marque(a: Article) -> bool:
        return m is not None and a.marque is not None and marques.normaliser(a.marque) == m

    def meme_categorie(a: Article) -> bool:
        # Les catégories de sourcing sont plus fines (« Polaire / zip ») : on compare le premier mot.
        if c is None or a.categorie is None:
            return False
        cat = marques.normaliser(a.categorie)
        return cat == c or c.startswith(cat) or cat.startswith(c.split(" ")[0])

    for base, filtre in (
        ("marque+categorie", lambda a: meme_marque(a) and meme_categorie(a)),
        ("marque", meme_marque),
        ("categorie", meme_categorie),
    ):
        membres = [a for a in vendus if filtre(a)]
        if membres:
            return _perf(membres, base)
    return Perf()


def perf_pistes(db: Session, pistes: list[PisteSourcing]) -> dict[int, Perf]:
    vendus = [a for a in tous_les_articles(db) if est_vendu(a)]
    resultat = {}
    for p in pistes:
        categorie = p.categorie or marques.detecter_categorie(p.produit)
        resultat[p.id] = perf_historique(vendus, p.marque, categorie)
    return resultat
