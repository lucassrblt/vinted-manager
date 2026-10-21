"""Rapprochement d'un mail de vente avec les articles en ligne (recherche floue sur le titre)."""

import re
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import Select, exists, or_, select
from sqlalchemy.orm import Session

from app.models import Article, Vente
from app.models.enums import StatutArticle
from app.services.marques import detecter_marque, normaliser

STATUTS_A_COMPLETER = [StatutArticle.VENDU, StatutArticle.ENVOYE, StatutArticle.LIVRE]

# Rapprochement automatique : un seul candidat nettement devant, avec un score élevé.
SEUIL_AUTO = 90.0
ECART_AUTO = 15.0
BONUS_PRIX = 10.0
BONUS_PRIX_REEL = 20.0
SCORE_MIN = 40.0  # en dessous, la suggestion n'aide pas
NB_CANDIDATS = 5


@dataclass
class Candidat:
    article_id: int
    nom: str
    taille: str | None
    prix_vente: Decimal | None
    score: float
    # Article déjà marqué vendu (import Excel) sans vente enregistrée : le mail complète sa vente.
    deja_vendu: bool = False


def _mots(texte: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", normaliser(texte)).split())


def score_titre(titre: str, article: Article) -> float:
    """Moyenne de deux mesures : `token_set` tolère les mots en plus (titre d'annonce plus long),
    `token_sort` pénalise les différences (« bleu marine » contre « blanc »)."""
    cible = _mots(titre)
    noms = [article.nom] + ([article.titre_annonce] if article.titre_annonce else [])
    return max(
        (fuzz.token_set_ratio(cible, _mots(n)) + fuzz.token_sort_ratio(cible, _mots(n))) / 2 for n in noms
    )


def du_compte(requete: Select[Article], compte_id: int | None) -> Select[Article]:
    """Limite aux articles de ce compte Vinted (ou pas encore attribués à un compte)."""
    if compte_id is None:
        return requete
    return requete.where(or_(Article.compte_id.is_(None), Article.compte_id == compte_id))


def sans_vente_enregistree() -> Any:
    """Article vendu à l'import (Excel) dont aucune vente n'est encore rattachée."""
    return Article.statut.in_(STATUTS_A_COMPLETER) & ~exists().where(Vente.article_id == Article.id)


def candidats(
    db: Session,
    titre: str | None,
    prix: Decimal | None,
    compte_id: int | None = None,
    date_mail: datetime | None = None,
) -> list[Candidat]:
    """Articles pouvant correspondre à un mail de vente : ceux en ligne, et ceux déjà marqués vendus
    à l'import sans vente rattachée (relecture de l'historique des mails)."""
    requete = select(Article).where(or_(Article.statut == StatutArticle.EN_LIGNE, sans_vente_enregistree()))
    articles = db.scalars(du_compte(requete, compte_id)).all()
    resultat = []
    marque_titre = detecter_marque(titre) if titre else None
    taille_titre = taille_du_titre(titre)
    for a in articles:
        if date_mail and a.date_achat and a.date_achat > date_mail.date():
            continue  # acheté après la vente : impossible
        marque_article = a.marque or detecter_marque(a.nom)
        if marque_titre and marque_article and normaliser(marque_titre) != normaliser(marque_article):
            continue  # une polaire Patagonia n'est pas un pull Ralph Lauren
        if taille_titre and a.taille and normaliser(a.taille).replace(" ", "") != taille_titre:
            continue  # « taille M » dans l'annonce : un article en L ne convient pas
        deja_vendu = a.statut != StatutArticle.EN_LIGNE
        score = score_titre(titre, a) if titre else 0.0
        prix_article = (a.prix_vente_reel or a.prix_vente_cible) if deja_vendu else a.prix_vente_cible
        if deja_vendu and prix is not None and a.prix_vente_reel is not None:
            # Vendu à l'import : le prix de vente réel est connu, c'est un indice fort dans les deux sens.
            score += BONUS_PRIX_REEL if abs(prix - a.prix_vente_reel) <= Decimal("0.5") else -BONUS_PRIX_REEL
        elif prix is not None and prix_article is not None and abs(prix - prix_article) <= Decimal("0.5"):
            score += BONUS_PRIX  # prix de la vente = prix affiché (à 50 centimes près)
        if score >= SCORE_MIN:
            # Score non plafonné (le bonus prix peut dépasser 100) : l'écart entre candidats reste juste.
            resultat.append(Candidat(a.id, a.nom, a.taille, prix_article, round(score, 1), deja_vendu))
    resultat.sort(key=lambda c: c.score, reverse=True)
    return resultat[:NB_CANDIDATS]


def taille_du_titre(titre: str | None) -> str | None:
    m = re.search(r"\btaille\s+([a-z0-9]{1,4}(?:/[a-z0-9]{1,4})?)\b", normaliser(titre or ""))
    return m.group(1) if m else None


def _identiques(a: Candidat, b: Candidat) -> bool:
    return (normaliser(a.nom), a.taille, a.prix_vente, a.deja_vendu) == (
        normaliser(b.nom),
        b.taille,
        b.prix_vente,
        b.deja_vendu,
    )


def choix_automatique(liste: list[Candidat]) -> Candidat | None:
    if not liste or liste[0].score < SEUIL_AUTO:
        return None
    # Ex aequo entre exemplaires strictement identiques (même nom, taille, prix) : n'importe lequel convient.
    proches = [c for c in liste[1:] if liste[0].score - c.score < ECART_AUTO]
    if proches and not all(_identiques(liste[0], c) for c in proches):
        return None
    return liste[0]
