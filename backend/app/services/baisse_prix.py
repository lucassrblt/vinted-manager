"""Baisse de prix automatique (section 10.2) : −5 % une seule fois par article, 48 à 72 h après la publication
sans vente, arrondi aux 50 centimes, jamais sous le plancher, jamais après une republication.

L'extension relit l'annonce complète avant de la modifier : si un champ manque pour reconstruire l'objet
`item`, elle n'envoie rien (une modification partielle effacerait des champs). Dans ce cas, le module est
coupé pour ce compte et Lucas est prévenu (capture de la page d'édition à faire, section 13.5).
"""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, CompteVinted, Parametres, TacheVinted
from app.models.enums import StatutArticle
from app.services import alertes, brouillons, file_vinted, horaires, offres, reglages, taches

PREFIXE_CHAMP_MANQUANT = "Champ manquant"
# Au-delà de 72 h (+ 24 h si le PC était éteint), l'article est hors de la fenêtre : pas de baisse tardive.
MARGE_RATTRAPAGE = timedelta(hours=24)


def echeance(article: Article, r: dict[str, float]) -> timedelta:
    """Délai propre à l'article, tiré entre 48 et 72 h (stable d'un passage à l'autre)."""
    return timedelta(hours=taches.alea(f"baisse-{article.id}", r["delai_min_heures"], r["delai_max_heures"]))


def nouveau_prix(article: Article, baisse_pct: float, plancher_pct: float) -> Decimal | None:
    if article.prix_vente_cible is None:
        return None
    affiche = article.prix_vente_cible
    plancher = offres.plancher_vinted(article.prix_initial or affiche, plancher_pct)
    prix = max(plancher, offres.arrondi_50(affiche * (1 - Decimal(str(baisse_pct)) / 100)))
    return prix if prix < affiche else None


def _en_attente(db: Session, compte: CompteVinted, article: Article) -> bool:
    return bool(
        db.scalar(
            select(TacheVinted.id)
            .where(
                TacheVinted.compte_id == compte.id,
                TacheVinted.article_id == article.id,
                TacheVinted.type.in_(("modifier_prix", "republication")),
                TacheVinted.statut.in_(("a_faire", "a_valider", "en_cours")),
            )
            .limit(1)
        )
    )


def planifier(db: Session) -> int:
    """Toutes les heures : baisses dues (articles publiés par l'app ou détectés au dressing, jamais importés)."""
    params = db.get(Parametres, 1)
    if params is not None and not params.automatisation_active:
        return 0
    maintenant = horaires.maintenant()
    n = 0
    for compte in db.scalars(select(CompteVinted).where(CompteVinted.jeton_extension_hash.is_not(None))):
        if not brouillons.compte_pret(compte) or not reglages.module_actif(compte, "prix"):
            continue
        r = reglages.du_compte(compte)["prix"]
        for a in db.scalars(
            select(Article).where(
                Article.compte_id == compte.id,
                Article.statut == StatutArticle.EN_LIGNE,
                Article.vinted_item_id.is_not(None),
                Article.baisse_prix_le.is_(None),
                Article.republications == 0,  # pas de nouvelle baisse après une republication
                Article.importe_vinted.is_(False),  # date de publication inconnue : pas de baisse automatique
            )
        ):
            publie = a.derniere_publication_le or a.date_publication
            if publie is None or _en_attente(db, compte, a):
                continue
            age = maintenant - publie
            if age < echeance(a, r) or age > timedelta(hours=r["delai_max_heures"]) + MARGE_RATTRAPAGE:
                continue
            prix = nouveau_prix(a, r["baisse_pct"], r["plancher_pct"])
            a.baisse_prix_le = maintenant
            if prix is None:
                alertes.journaliser(
                    db,
                    compte,
                    "prix",
                    f"{a.nom} : aucune baisse possible au-dessus du plancher.",
                    article_id=a.id,
                )
                continue
            assert a.prix_vente_cible is not None
            taches.creer(
                db, compte, "modifier_prix",
                {"item_id": a.vinted_item_id, "prix_actuel": brouillons.prix_texte(a.prix_vente_cible),
                 "nouveau_prix": brouillons.prix_texte(prix), "ai_photo": a.ai_photo_declare, "article": a.nom},
                a.id, maintenant + horaires.delai(0, 30 * 60), cle=f"baisse:{a.id}",
            )  # fmt: skip
            alertes.journaliser(
                db,
                compte,
                "prix",
                f"{a.nom} : baisse programmée de {a.prix_vente_cible} € à {prix} €.",
                article_id=a.id,
            )
            n += 1
    alertes.valider(db)
    return n


@file_vinted.apres("modifier_prix")
def _apres(db: Session, compte: CompteVinted, tache: TacheVinted, ok: bool) -> None:
    article = db.get(Article, tache.article_id) if tache.article_id else None
    if ok and article is not None:
        article.prix_avant_baisse = article.prix_vente_cible
        article.prix_vente_cible = Decimal(str(tache.payload["nouveau_prix"]))
        alertes.journaliser(
            db,
            compte,
            "prix",
            f"{article.nom} : prix baissé à {article.prix_vente_cible} €.",
            article_id=article.id,
        )
        return
    if ok:
        return
    erreur = tache.erreur or ""
    if erreur.startswith(PREFIXE_CHAMP_MANQUANT):
        # Une seule tentative suffit : toutes les suivantes échoueraient pareil. On coupe le module.
        reglages.enregistrer(compte, {"modules": {"prix": False}})
        alertes.alerter(
            db, compte, "tache_erreur", "Baisse de prix automatique coupée",
            f"{erreur} Aucune modification n'a été envoyée. Capture le chargement de la page d'édition d'une annonce "
            "(DevTools → Réseau, « Save all as HAR ») pour compléter la reconstruction, puis réactive le module.",
            article_id=tache.article_id,
        )  # fmt: skip
    else:
        alertes.alerter(
            db, compte, "tache_erreur", "Baisse de prix en échec", erreur, article_id=tache.article_id
        )
