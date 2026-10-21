from datetime import UTC, datetime
from decimal import Decimal as D

import pytest

from app.services import calculs, marques
from app.services.calculs import Indicateur
from app.services.remise import repartir_remise


def test_marge_et_coefficient_comme_excel() -> None:
    # Ligne Excel : T-shirt CDG Play, achat 7,67 €, vente 24 €
    assert calculs.marge_nette(D("24"), D("7.67")) == D("16.33")
    assert calculs.marge_pct(D("24"), D("7.67")) == pytest.approx(D("2.129074316"), rel=D("1e-9"))
    assert calculs.coefficient(D("24"), D("7.67")) == pytest.approx(D("3.129074316"), rel=D("1e-9"))


def test_valeurs_manquantes() -> None:
    assert calculs.marge_nette(None, D("10")) is None
    assert calculs.coefficient(D("10"), D("0")) is None
    assert calculs.coefficient(D("10"), None) is None
    assert calculs.marge_pct(D("10"), D("0")) is None


@pytest.mark.parametrize(
    ("coeff", "attendu"),
    [
        (D("1.48"), Indicateur.SOUS_OBJECTIF),
        (D("1.99"), Indicateur.SOUS_OBJECTIF),
        (D("2"), Indicateur.OK),
        (D("3.13"), Indicateur.OK),
        (D("4"), Indicateur.OK),
        (D("5.94"), Indicateur.AU_DESSUS),
        (None, None),
    ],
)
def test_indicateur(coeff: D | None, attendu: Indicateur | None) -> None:
    assert calculs.indicateur(coeff) == attendu


def test_indicateur_bornes_configurables() -> None:
    assert calculs.indicateur(D("2.5"), D("3"), D("5")) == Indicateur.SOUS_OBJECTIF


def test_delai_vente() -> None:
    pub = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)
    vente = datetime(2026, 10, 3, 16, 0, tzinfo=UTC)
    assert calculs.delai_vente_heures(pub, vente) == 54
    assert calculs.delai_vente_jours(pub, vente) == 2.25
    assert calculs.delai_vente_heures(None, vente) is None


def test_sell_through() -> None:
    assert calculs.sell_through(13, 14) == D(13) / D(14)
    assert calculs.sell_through(0, 0) is None


def test_prix_achat_net() -> None:
    assert calculs.prix_achat_net(D("17.64"), D("0.97")) == D("16.67")
    assert calculs.prix_achat_net(D("10"), None) == D("10.00")


# --- Répartition de la remise ---------------------------------------------------------------


def test_remise_somme_exacte_et_prorata() -> None:
    # Composition réelle du Batch 2 : 8 pulls, 4 t-shirts, 4 bonnets, remise de 10,56 €
    bruts = [D("17.64")] * 8 + [D("7.85")] * 4 + [D("4.98")] * 4
    remises = repartir_remise(bruts, D("10.56"))
    assert sum(remises) == D("10.56")
    # Même prix brut -> même remise à un centime près (les centimes restants sont répartis)
    assert max(remises[:8]) - min(remises[:8]) <= D("0.01")
    # Comme dans l'Excel : ~0,97 € pour un pull à 17,64 €, ~0,43 € pour un t-shirt à 7,85 €
    assert all(r in (D("0.97"), D("0.98")) for r in remises[:8])
    assert all(r in (D("0.43"), D("0.44")) for r in remises[8:12])
    assert all(r in (D("0.27"), D("0.28")) for r in remises[12:])


def test_remise_nulle_ou_vide() -> None:
    assert repartir_remise([], D("5")) == []
    assert repartir_remise([D("10"), D("20")], D("0")) == [D("0.00"), D("0.00")]


def test_remise_superieure_au_total() -> None:
    with pytest.raises(ValueError):
        repartir_remise([D("10")], D("11"))


def test_remise_proportionnelle() -> None:
    assert repartir_remise([D("30"), D("10")], D("4")) == [D("3.00"), D("1.00")]


# --- Déduction marque / catégorie / couleur -------------------------------------------------


@pytest.mark.parametrize(
    ("nom", "marque", "categorie", "couleur"),
    [
        ("T-shirt Comme des Garçons Play cœur jaune - noir", "Comme des Garçons Play", "T-shirt", "Noir"),
        ("Hoodie Carhartt WIP - gris clair", "Carhartt WIP", "Hoodie", "Gris clair"),
        ("Pull demi-zip polaire Ralph Lauren - Tibet", "Ralph Lauren", "Pull", "Tibet"),
        ("CDG Play hoodie zippé", "Comme des Garçons Play", "Hoodie", None),
        ("Patagonia shell / coupe-vent capuche", "Patagonia", "Coupe-vent", None),
        ("Patagonia colorblock / Snap-T style", "Patagonia", "Polaire", None),
        ("Casquette Ralph Lauren - noir logo rouge", "Ralph Lauren", "Casquette", "Noir logo rouge"),
        ("Coupe-vent The North Face - noir", "The North Face", "Coupe-vent", "Noir"),
        ("Branded sweater - lot mix (3/10)", None, "Pull", None),
        ("Bonnet Ralph Lauren - blanc", "Ralph Lauren", "Bonnet", "Blanc"),
        ("Polaire Nike ACG - noir", "Nike ACG", "Polaire", "Noir"),
    ],
)
def test_deduction(nom: str, marque: str | None, categorie: str | None, couleur: str | None) -> None:
    assert marques.detecter_marque(nom) == marque
    assert marques.detecter_categorie(nom) == categorie
    assert marques.detecter_couleur(nom) == couleur
