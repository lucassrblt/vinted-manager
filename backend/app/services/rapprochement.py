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
from app.services.marques import normaliser

STATUTS_A_COMPLETER = [StatutArticle.VENDU, StatutArticle.ENVOYE, StatutArticle.LIVRE]

# Rapprochement automatique : un seul candidat nettement devant, avec un score élevé.
SEUIL_AUTO = 90.0
ECART_AUTO = 15.0
BONUS_PRIX = 10.0
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
    for a in articles:
        if date_mail and a.date_achat and a.date_achat > date_mail.date():
            continue  # acheté après la vente : impossible
        deja_vendu = a.statut != StatutArticle.EN_LIGNE
        score = score_titre(titre, a) if titre else 0.0
        prix_article = (a.prix_vente_reel or a.prix_vente_cible) if deja_vendu else a.prix_vente_cible
        # Bonus si le prix de la vente correspond au prix affiché (à 50 centimes près).
        if prix is not None and prix_article is not None and abs(prix - prix_article) <= Decimal("0.5"):
            score += BONUS_PRIX
        if score > 0:
            # Score non plafonné (le bonus prix peut dépasser 100) : l'écart entre candidats reste juste.
            resultat.append(Candidat(a.id, a.nom, a.taille, prix_article, round(score, 1), deja_vendu))
    resultat.sort(key=lambda c: c.score, reverse=True)
    return resultat[:NB_CANDIDATS]


def choix_automatique(liste: list[Candidat]) -> Candidat | None:
    if not liste or liste[0].score < SEUIL_AUTO:
        return None
    if len(liste) > 1 and liste[0].score - liste[1].score < ECART_AUTO:
        return None
    return liste[0]
