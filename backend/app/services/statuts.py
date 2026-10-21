"""Changement de statut d'un article, toujours horodaté dans HistoriqueStatut."""

from datetime import datetime

from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Article, HistoriqueStatut
from app.models.enums import StatutArticle

# Date de l'article renseignée automatiquement quand il entre dans un statut (si elle est vide).
DATE_PAR_STATUT: dict[StatutArticle, str] = {
    StatutArticle.RECU_A_PUBLIER: "date_reception",
    StatutArticle.EN_LIGNE: "date_publication",
    StatutArticle.VENDU: "date_vente",
    StatutArticle.ENVOYE: "date_envoi",
    StatutArticle.LIVRE: "date_livraison",
}


def changer_statut(
    db: Session,
    article: Article,
    nouveau: StatutArticle,
    quand: datetime | None = None,
    commentaire: str | None = None,
    forcer_date: bool = False,
) -> None:
    """Passe l'article dans `nouveau` et enregistre la transition.

    `forcer_date` écrase la date existante (ex. « publié aujourd'hui » sur un article republié).
    """
    quand = quand or utcnow()
    ancien = article.statut
    if ancien == nouveau:
        return
    article.statut = nouveau
    champ = DATE_PAR_STATUT.get(nouveau)
    if champ and (forcer_date or getattr(article, champ) is None):
        setattr(article, champ, quand)
    if nouveau == StatutArticle.LITIGE:
        article.litige = True
    db.add(
        HistoriqueStatut(
            article=article,
            ancien_statut=ancien,
            nouveau_statut=nouveau,
            date=quand,
            commentaire=commentaire,
        )
    )
