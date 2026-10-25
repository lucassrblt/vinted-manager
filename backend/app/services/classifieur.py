"""Moteur de règles de classement et d'extraction des mails Vinted.

Une règle = des conditions (toutes les catégories renseignées doivent correspondre ; au sein d'une
liste, une seule valeur suffit) + des regex d'extraction. Les règles sont testées par priorité
croissante : la première qui correspond donne le type du mail.
"""

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.services.email_parser import MailLu
from app.services.marques import normaliser

MOIS = {
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
    "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
}  # fmt: skip

# Champs d'extraction reconnus (les autres clés d'une règle sont ignorées).
CHAMPS_EXTRACTION = (
    "prix",
    "montant_offre",
    "prix_affiche",
    "titre_article",
    "numero_commande",
    "acheteur",
    "date_limite",
    "lien_bordereau",
)


class RegleLike(Protocol):
    id: int
    nom: str
    type_cible: str
    conditions: dict[str, Any]
    extraction: dict[str, str]
    priorite: int
    active: bool


@dataclass
class Resultat:
    type: str | None
    regle_id: int | None = None
    regle_nom: str | None = None
    donnees: dict[str, Any] = field(default_factory=dict)


def _contient(texte: str, valeurs: list[str]) -> bool:
    t = normaliser(texte)
    return any(normaliser(v) in t for v in valeurs if v.strip())


def _regex(texte: str, motif: str) -> re.Match[str] | None:
    try:
        return re.search(motif, texte, re.IGNORECASE | re.MULTILINE)
    except re.error:
        return None


def correspond(regle: RegleLike, mail: MailLu) -> bool:
    c = regle.conditions or {}
    texte = mail.texte_complet
    tests: list[bool] = []
    if c.get("expediteurs"):
        tests.append(_contient(mail.expediteur, c["expediteurs"]))
    if c.get("sujet_contient"):
        tests.append(_contient(mail.sujet, c["sujet_contient"]))
    if c.get("corps_contient"):
        tests.append(_contient(texte, c["corps_contient"]))
    if c.get("sujet_regex"):
        tests.append(_regex(mail.sujet, c["sujet_regex"]) is not None)
    if c.get("corps_regex"):
        tests.append(_regex(texte, c["corps_regex"]) is not None)
    if c.get("piece_jointe_pdf"):
        tests.append(any(p.mime == "application/pdf" for p in mail.pieces_jointes))
    # Une règle sans aucune condition ne correspond à rien (évite de tout avaler par erreur).
    return bool(tests) and all(tests)


def montant(texte: str) -> Decimal | None:
    propre = re.sub(r"[\s  €]", "", texte).replace(",", ".")
    try:
        return Decimal(propre).quantize(Decimal("0.01"))
    except InvalidOperation:
        return None


def date_texte(texte: str, reference: datetime | None) -> datetime | None:
    """« 23/10/2026 », « 23/10 », « 23 octobre » ou « 23 octobre 2026 » -> fin de journée, heure de Paris."""
    ref = reference or datetime.now(UTC)
    t = normaliser(texte)
    jour: date | None = None
    annee_explicite = False
    if m := re.search(r"(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?", t):
        annee_explicite = m.group(3) is not None
        j, mo = int(m.group(1)), int(m.group(2))
        a = int(m.group(3)) if m.group(3) else ref.year
        a = a + 2000 if a < 100 else a
        try:
            jour = date(a, mo, j)
        except ValueError:
            return None
    elif m := re.search(r"(\d{1,2})\s+(" + "|".join(MOIS) + r")(?:\s+(\d{4}))?", t):
        annee_explicite = m.group(3) is not None
        a = int(m.group(3)) if m.group(3) else ref.year
        try:
            jour = date(a, MOIS[m.group(2)], int(m.group(1)))
        except ValueError:
            return None
    if jour is None:
        return None
    if not annee_explicite and jour < ref.date() - timedelta(days=180):
        jour = jour.replace(year=jour.year + 1)  # « 3 janvier » reçu fin décembre
    return datetime.combine(jour, time(23, 59), ZoneInfo(get_settings().timezone))


def extraire(regle: RegleLike, mail: MailLu) -> dict[str, Any]:
    texte = f"{mail.sujet}\n{mail.texte_complet}"
    donnees: dict[str, Any] = {}
    for champ, motif in (regle.extraction or {}).items():
        if champ not in CHAMPS_EXTRACTION or not motif:
            continue
        if champ == "lien_bordereau":
            for libelle, url in mail.liens:
                if _regex(f"{libelle} {url}", motif):
                    donnees[champ] = url
                    break
            continue
        m = _regex(texte, motif)
        if not m:
            continue
        # Groupe nommé « v » en priorité, sinon le premier groupe capturé, sinon tout le motif.
        captures = [g for g in (m.groupdict().get("v"), *m.groups()) if g]
        brut = (captures[0] if captures else m.group(0)).strip()
        if champ in ("prix", "montant_offre", "prix_affiche"):
            valeur = montant(brut)
            if valeur is not None:
                donnees[champ] = str(valeur)
        elif champ == "date_limite":
            d = date_texte(brut, mail.date)
            if d:
                donnees[champ] = d.isoformat()
        else:
            donnees[champ] = brut[:255]
    return donnees


def classer(regles: Sequence[RegleLike], mail: MailLu) -> Resultat:
    for regle in sorted((r for r in regles if r.active), key=lambda r: (r.priorite, r.id)):
        if correspond(regle, mail):
            return Resultat(
                type=regle.type_cible, regle_id=regle.id, regle_nom=regle.nom, donnees=extraire(regle, mail)
            )
    return Resultat(type=None)


def ajouter_jours_ouvres(depart: datetime, jours: int) -> datetime:
    d = depart
    while jours > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            jours -= 1
    return d
