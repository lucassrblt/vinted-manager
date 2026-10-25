"""Synchronisation du dressing Vinted (événement « dressing » de l'extension, toutes les 30 min).

Chaque annonce en ligne est rattachée à un article : d'abord par `vinted_item_id`, puis par le brouillon
publié (même identifiant), par titre exact, enfin par la recherche floue déjà utilisée pour les mails.
Sans correspondance, un article « importé de Vinted » est créé (signalé dans l'app). Les brouillons
(`is_draft`) ne sont pas des annonces en ligne.
"""

from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Article, CompteVinted
from app.models.enums import EtatArticle, StatutArticle
from app.services import alertes, brouillons, file_vinted, horaires, rapprochement
from app.services.marques import normaliser
from app.services.notifications import notifier
from app.services.statuts import changer_statut

ETATS_VINTED = {
    "neuf avec etiquette": EtatArticle.NEUF_ETIQUETTE,
    "neuf sans etiquette": EtatArticle.NEUF_SANS_ETIQUETTE,
    "tres bon etat": EtatArticle.TRES_BON,
    "bon etat": EtatArticle.BON,
    "satisfaisant": EtatArticle.SATISFAISANT,
}
RATTACHABLES = (StatutArticle.RECU_A_PUBLIER, StatutArticle.EN_LIGNE)
# Traitements appelés après une lecture complète, avec les annonces encore en vente (phase 7 : ventes).
APRES_SYNCHRO: list[Callable[[Session, CompteVinted, set[int]], None]] = []


def prix(item: dict[str, Any]) -> Decimal | None:
    brut = item.get("price")
    montant = brut.get("amount") if isinstance(brut, dict) else brut
    try:
        return Decimal(str(montant)).quantize(Decimal("0.01")) if montant is not None else None
    except InvalidOperation:
        return None


def ferme(item: dict[str, Any]) -> bool:
    return bool(item.get("is_closed")) or bool(item.get("item_closing_action"))


def _du_compte(compte: CompteVinted) -> Any:
    return or_(Article.compte_id.is_(None), Article.compte_id == compte.id)


def _rattacher(db: Session, compte: CompteVinted, item: dict[str, Any]) -> Article | None:
    item_id = int(item["id"])
    for colonne in (Article.vinted_item_id, Article.vinted_draft_id):
        trouve = db.scalar(select(Article).where(colonne == item_id).limit(1))
        if trouve is not None:
            if trouve.compte_id not in (None, compte.id):
                alertes.journaliser(
                    db,
                    compte,
                    "dressing",
                    f"Annonce {item_id} rattachée à un article d'un autre compte : ignorée.",
                    "erreur",
                )
                return None
            return trouve
    titre = str(item.get("title") or "")
    candidats = list(
        db.scalars(
            select(Article).where(
                _du_compte(compte), Article.vinted_item_id.is_(None), Article.statut.in_(RATTACHABLES)
            )
        )
    )
    exacts = [
        a for a in candidats if normaliser(titre) in {normaliser(a.titre_annonce or ""), normaliser(a.nom)}
    ]
    if len(exacts) == 1:
        return exacts[0]
    marque = normaliser(str(item.get("brand") or ""))
    taille = normaliser(str(item.get("size") or "")).replace(" ", "")
    prix_item = prix(item)
    liste = []
    for a in exacts or candidats:
        if marque and a.marque and normaliser(a.marque) != marque:
            continue
        if taille and a.taille and normaliser(a.taille).replace(" ", "") != taille:
            continue
        score = rapprochement.score_titre(titre, a)
        if (
            prix_item is not None
            and a.prix_vente_cible is not None
            and abs(prix_item - a.prix_vente_cible) <= Decimal("0.5")
        ):
            score += rapprochement.BONUS_PRIX
        if score >= rapprochement.SCORE_MIN:
            liste.append(rapprochement.Candidat(a.id, a.nom, a.taille, a.prix_vente_cible, round(score, 1)))
    liste.sort(key=lambda c: c.score, reverse=True)
    choix = rapprochement.choix_automatique(liste)
    return db.get(Article, choix.article_id) if choix else None


def _importer(db: Session, compte: CompteVinted, item: dict[str, Any]) -> Article:
    titre = str(item.get("title") or f"Annonce Vinted {item['id']}")[:255]
    article = Article(
        nom=titre,
        titre_annonce=titre[:120],
        marque=(str(item["brand"])[:120] if item.get("brand") else None),
        taille=(str(item["size"])[:40] if item.get("size") else None),
        etat=ETATS_VINTED.get(normaliser(str(item.get("status") or ""))),
        prix_vente_cible=prix(item),
        statut=StatutArticle.EN_LIGNE,
        compte_id=compte.id,
        importe_vinted=True,
        date_publication=horaires.maintenant(),
        notes="Importé depuis le dressing Vinted : coût d'achat et batch à compléter.",
    )
    db.add(article)
    db.flush()
    return article


def _mettre_a_jour(db: Session, compte: CompteVinted, article: Article, item: dict[str, Any]) -> None:
    article.vinted_item_id = int(item["id"])
    article.compte_id = article.compte_id or compte.id
    article.vinted_vu_le = horaires.maintenant()
    article.vinted_vues = (
        item.get("view_count") if isinstance(item.get("view_count"), int) else article.vinted_vues
    )
    article.vinted_favoris = (
        item.get("favourite_count")
        if isinstance(item.get("favourite_count"), int)
        else article.vinted_favoris
    )
    urls = [p.get("full_size_url") or p.get("url") for p in item.get("photos") or [] if isinstance(p, dict)]
    if urls:
        article.vinted_photos = [u for u in urls if isinstance(u, str)]
    if ferme(item) or article.statut not in RATTACHABLES:
        return  # vendue ou fermée : on ne touche ni au prix ni au statut
    montant = prix(item)
    if montant is not None:
        article.prix_vente_cible = montant  # prix affiché sur Vinted
        brouillons.fixer_prix_initial(article, montant)
    if article.statut == StatutArticle.RECU_A_PUBLIER:
        changer_statut(db, article, StatutArticle.EN_LIGNE, commentaire="En ligne sur Vinted (dressing)")


def synchroniser(db: Session, compte: CompteVinted, donnees: dict[str, Any]) -> dict[str, Any]:
    items = [i for i in donnees.get("items") or [] if isinstance(i, dict) and i.get("id") is not None]
    vus: set[int] = set()
    importes: list[Article] = []
    rattaches = 0
    for item in items:
        if item.get("is_draft"):
            continue
        if not ferme(item):
            vus.add(int(item["id"]))  # annonces encore en vente
        article = _rattacher(db, compte, item)
        if article is None:
            if ferme(item):
                continue  # ancienne vente : pas d'import
            article = _importer(db, compte, item)
            importes.append(article)
        else:
            rattaches += 1
        _mettre_a_jour(db, compte, article, item)
    db.flush()
    if importes:
        noms = ", ".join(a.nom for a in importes[:5]) + ("…" if len(importes) > 5 else "")
        alertes.journaliser(
            db, compte, "dressing", f"{len(importes)} annonce(s) importée(s) de Vinted : {noms}", "alerte"
        )
        notifier(
            db,
            "extension",
            f"[{compte.nom}] {len(importes)} annonce(s) importée(s) de Vinted",
            "/stock",
            corps=noms,
        )
    # Lecture complète (toutes les pages) : on peut conclure qu'une annonce absente a disparu.
    if donnees.get("complet") is True:
        for traitement in APRES_SYNCHRO:
            traitement(db, compte, vus)
    return {"rattaches": rattaches, "importes": len(importes)}


file_vinted.EVENEMENTS["dressing"] = synchroniser
