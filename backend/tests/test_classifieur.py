"""Classement et extraction : mails synthétiques + vrais .eml déposés dans fixtures/emails/<type>/.

Pour vérifier aussi l'extraction d'un vrai mail, ajoute à côté du .eml un fichier .json du même nom
avec les valeurs attendues, par exemple : {"prix": "45.00", "titre_article": "Pull ..."}.
"""

import json
from pathlib import Path

import pytest
from sqlalchemy.orm import Session

from app.models import RegleClassement
from app.seed.regles import REGLES_INITIALES
from app.services import classifieur
from app.services.email_parser import lire_mail
from tests import mails_synthetiques as ms

FIXTURES = Path(__file__).parent.parent / "fixtures" / "emails"
VRAIS_EML = sorted(FIXTURES.glob("*/*.eml"))


def _regles() -> list[RegleClassement]:
    return [RegleClassement(id=i, active=True, **r) for i, r in enumerate(REGLES_INITIALES, start=1)]


@pytest.mark.parametrize("type_attendu", list(ms.PAR_TYPE))
def test_classement_synthetique(type_attendu: str) -> None:
    resultat = classifieur.classer(_regles(), lire_mail(ms.PAR_TYPE[type_attendu]))
    assert resultat.type == type_attendu


def test_mail_inconnu_non_classe() -> None:
    assert classifieur.classer(_regles(), lire_mail(ms.INCONNU)).type is None


def test_expediteur_non_vinted_ignore() -> None:
    brut = ms.mail("Ton article a été vendu !", "…", expediteur="Arnaque <promo@exemple.com>")
    assert classifieur.classer(_regles(), lire_mail(brut)).type is None


def test_extraction_vente() -> None:
    d = classifieur.classer(_regles(), lire_mail(ms.VENTE)).donnees
    assert d["prix"] == "45.00"
    assert d["titre_article"] == "Pull demi-zip polaire Ralph Lauren - Noir"
    assert d["numero_commande"] == "8812345678"
    assert d["acheteur"] == "claire_75"
    assert d["date_limite"].startswith("2026-10-27T23:59")
    assert d["lien_bordereau"] == "https://www.vinted.fr/shipping/label/123"


def test_extraction_offre() -> None:
    d = classifieur.classer(_regles(), lire_mail(ms.OFFRE)).donnees
    assert d["montant_offre"] == "35.00"
    assert d["acheteur"] == "sophie.b"


@pytest.mark.parametrize(
    ("texte", "attendu"),
    [
        ("23/10/2026", "2026-10-23"),
        ("23/10", "2026-10-23"),
        ("5 novembre", "2026-11-05"),
        ("3 janvier", "2027-01-03"),
    ],
)
def test_dates_limites(texte: str, attendu: str) -> None:
    d = classifieur.date_texte(texte, ms.DATE)
    assert d is not None and d.date().isoformat() == attendu


def test_priorite_et_regle_inactive() -> None:
    regles = _regles()
    # « livré » est testé avant « vente » ; désactivé, le mail n'est plus reconnu comme livraison
    for r in regles:
        if r.type_cible == "livre":
            r.active = False
    assert classifieur.classer(regles, lire_mail(ms.LIVRE)).type != "livre"


def test_regex_invalide_ne_plante_pas() -> None:
    r = RegleClassement(id=1, nom="x", type_cible="autre", priorite=1, active=True,
                        conditions={"corps_regex": "("}, extraction={"prix": "("})  # fmt: skip
    assert classifieur.classer([r], lire_mail(ms.VENTE)).type is None


@pytest.mark.skipif(not VRAIS_EML, reason="Aucun .eml réel dans backend/fixtures/emails/<type>/")
@pytest.mark.parametrize("chemin", VRAIS_EML, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_vrais_mails(chemin: Path, db: Session, regles: None) -> None:
    from app.services.traitement import regles_actives

    resultat = classifieur.classer(regles_actives(db), lire_mail(chemin.read_bytes()))
    attendu = chemin.parent.name
    assert resultat.type == (None if attendu == "autre" else attendu), (
        f"{chemin.name} classé « {resultat.type} » au lieu de « {attendu} »"
    )
    attentes = chemin.with_suffix(".json")
    if attentes.exists():
        for champ, valeur in json.loads(attentes.read_text()).items():
            assert resultat.donnees.get(champ) == valeur, (
                f"{champ} : {resultat.donnees.get(champ)!r} ≠ {valeur!r}"
            )
