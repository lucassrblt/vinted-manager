"""Après-vente (section 10.3).

1. La vente est détectée par les mails (existant) et confirmée par la disparition de l'annonce du dressing.
2. Message de remerciement quelques minutes après, dans la conversation de l'acheteur (trouvée par l'extension
   dans la messagerie). Conversation introuvable : tâche en erreur, sans alerte.
3. Récapitulatif quotidien (17 h 30, réglable) sur Telegram : colis à préparer et PDF A4 des bordereaux
   (il remplace le rappel push de 9 h ; sans Telegram, le récapitulatif part en notification push).
4. Rappel la veille de la date limite d'envoi.
5. Évaluations : rien d'automatique. Litige ou retour : alerte immédiate (mails), aucune action.
"""

import random
from datetime import datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging import log
from app.models import Article, CompteVinted, Envoi, Parametres, TacheVinted, Vente
from app.models.enums import StatutArticle, StatutEnvoi
from app.services import (
    alertes,
    bordereaux,
    dressing,
    file_vinted,
    horaires,
    push,
    reglages,
    storage,
    taches,
    telegram,
)
from app.services.notifications import notifier

# Seules les ventes récentes reçoivent un remerciement (pas les anciennes, au premier lancement).
FENETRE_VENTE = timedelta(days=3)
A_PREPARER = (StatutEnvoi.A_IMPRIMER, StatutEnvoi.IMPRIME)


def message(modele: str, acheteur: str | None, article: Article) -> str:
    texte = modele.replace("{article}", article.titre_annonce or article.nom)
    texte = (
        texte.replace("{prenom}", acheteur)
        if acheteur
        else texte.replace(" {prenom}", "").replace("{prenom}", "")
    )
    return " ".join(texte.split(" ")).strip()


def ventes_disparues(db: Session, compte: CompteVinted, en_ligne: set[int]) -> None:
    """Après une lecture complète du dressing : les articles vendus (mail) dont l'annonce a disparu."""
    if not reglages.module_actif(compte, "apres_vente"):
        return
    maintenant = horaires.maintenant()
    modeles = reglages.du_compte(compte)["apres_vente"]["messages"]
    for article in db.scalars(
        select(Article).where(
            Article.compte_id == compte.id,
            Article.statut == StatutArticle.VENDU,
            Article.vinted_item_id.is_not(None),
        )
    ):
        if article.vinted_item_id in en_ligne:
            continue  # pas encore confirmée par le dressing
        vente = db.scalar(
            select(Vente).where(Vente.article_id == article.id).order_by(Vente.date_heure.desc()).limit(1)
        )
        if vente is None or vente.date_heure < maintenant - FENETRE_VENTE:
            continue
        cle = f"apres_vente:{vente.id}"
        if db.scalar(
            select(TacheVinted.id).where(TacheVinted.compte_id == compte.id, TacheVinted.cle == cle)
        ):
            continue  # remerciement déjà prévu ou envoyé
        taches.creer(
            db, compte, "message_apres_vente",
            {"item_id": article.vinted_item_id, "acheteur": vente.acheteur, "vente_id": vente.id, "article": article.nom,
             "texte": message(random.choice(modeles), vente.acheteur, article), "erreur_silencieuse": True},
            article.id, maintenant + horaires.delai(3 * 60, 10 * 60), cle=cle,
        )  # fmt: skip
        alertes.journaliser(
            db,
            compte,
            "apres_vente",
            f"Vente confirmée par le dressing : {article.nom}.",
            article_id=article.id,
        )


@file_vinted.apres("message_apres_vente")
def _apres(db: Session, compte: CompteVinted, tache: TacheVinted, ok: bool) -> None:
    if ok:
        alertes.journaliser(
            db,
            compte,
            "apres_vente",
            f"Remerciement envoyé : {tache.payload.get('article')}.",
            article_id=tache.article_id,
        )
    else:  # conversation introuvable, etc. : sans alerte (spécification)
        alertes.journaliser(
            db,
            compte,
            "apres_vente",
            f"Remerciement non envoyé : {tache.erreur}",
            article_id=tache.article_id,
        )


# --- Récapitulatif quotidien et rappels ------------------------------------------------------------


def _envois_a_preparer(db: Session) -> list[tuple[Envoi, Article]]:
    lignes = db.execute(
        select(Envoi, Article)
        .join(Vente, Vente.id == Envoi.vente_id)
        .join(Article, Article.id == Vente.article_id)
        .where(Envoi.statut.in_(A_PREPARER))
    ).all()
    return sorted(
        ((e, a) for e, a in lignes),
        key=lambda x: (
            x[0].date_limite_envoi is None,
            x[0].date_limite_envoi or horaires.maintenant(),
            x[0].id,
        ),
    )


def _heure(compte: CompteVinted | None) -> time:
    brut = (
        reglages.du_compte(compte)["apres_vente"]["heure_recap"]
        if compte
        else reglages.DEFAUTS["apres_vente"]["heure_recap"]
    )
    h, m = str(brut).split(":")
    return time(int(h), int(m))


def _du_jour(quand: datetime | None) -> bool:
    return quand is not None and horaires.local(quand).date() == horaires.local().date()


def _texte(envois: list[tuple[Envoi, Article]]) -> str:
    aujourdhui = horaires.local().date()
    lignes = [f"📦 {len(envois)} colis à préparer :"]
    for e, a in envois:
        limite = horaires.local(e.date_limite_envoi) if e.date_limite_envoi else None
        etat = ""
        if limite is not None:
            etat = " ⚠️ en retard" if limite.date() < aujourdhui else f" (avant le {limite:%d/%m})"
        imprime = " · bordereau imprimé" if e.statut == StatutEnvoi.IMPRIME else ""
        lignes.append(f"- {a.nom}{etat}{imprime}")
    return "\n".join(lignes)


def _pdf(envois: list[tuple[Envoi, Article]]) -> bytes | None:
    contenus = []
    for e, _ in envois:
        if e.fichier_bordereau and storage.chemin_absolu(e.fichier_bordereau).exists():
            contenus.append(storage.chemin_absolu(e.fichier_bordereau).read_bytes())
    if not contenus:
        return None
    try:
        return bordereaux.fusionner(contenus, format_10x15=False)  # A4
    except Exception:  # un bordereau illisible : le récapitulatif part quand même, sans PDF
        log.exception("recap_pdf_erreur")
        return None


def recapitulatif(db: Session) -> int:
    """À l'heure du récapitulatif de chaque compte (17 h 30 par défaut), une fois par jour."""
    local = horaires.local()
    envoyes = 0
    tous = _envois_a_preparer(db)
    for compte in db.scalars(select(CompteVinted).where(CompteVinted.telegram_chat_id.is_not(None))):
        if not reglages.module_actif(compte, "apres_vente") or _du_jour(compte.recap_envoye_le):
            continue
        if local.time() < _heure(compte):
            continue
        compte.recap_envoye_le = horaires.maintenant()
        # Ses colis, et ceux des articles sans compte (anciens articles importés de l'Excel).
        envois = [(e, a) for e, a in tous if a.compte_id in (compte.id, None)]
        if not envois:
            continue  # pas de récapitulatif « rien à faire »
        alertes.telegram_pour(db, compte, "recap", _texte(envois))
        pdf = _pdf(envois)
        if pdf:  # le PDF suit le message (la légende d'un document Telegram est limitée à 1 024 caractères)
            nom = f"bordereaux-{local:%Y%m%d}.pdf"
            alertes.telegram_pour(db, compte, "recap", "Bordereaux à imprimer (A4)", document=(nom, pdf))
        envoyes += 1
    _recap_push(db, local, tous)
    alertes.valider(db)
    return envoyes


def _recap_push(db: Session, local: datetime, envois: list[tuple[Envoi, Article]]) -> None:
    """Sans Telegram (ou sans compte relié), le récapitulatif part en notification push."""
    if telegram.configure() and db.scalar(
        select(CompteVinted.id).where(CompteVinted.telegram_chat_id.is_not(None)).limit(1)
    ):
        return
    params = db.get(Parametres, 1)
    if params is None or _du_jour(params.recap_push_le) or local.time() < _heure(None) or not envois:
        return
    params.recap_push_le = horaires.maintenant()
    retard = sum(
        1
        for e, _ in envois
        if e.date_limite_envoi and horaires.local(e.date_limite_envoi).date() < local.date()
    )
    corps = f"{len(envois)} colis à préparer" + (f" · {retard} en retard" if retard else "")
    push.envoyer(db, "rappel_envois", f"📦 {len(envois)} colis à envoyer", corps, "/envois")


def rappels_limite(db: Session) -> int:
    """La veille de la date limite d'envoi : un rappel par colis pas encore déposé."""
    maintenant = horaires.maintenant()
    n = 0
    for e, a in _envois_a_preparer(db):
        if e.rappel_limite_le is not None or e.date_limite_envoi is None:
            continue
        if not maintenant < e.date_limite_envoi <= maintenant + timedelta(hours=24):
            continue
        e.rappel_limite_le = maintenant
        compte = db.get(CompteVinted, a.compte_id) if a.compte_id else None
        limite = horaires.local(e.date_limite_envoi)
        titre = f"⏰ À déposer avant le {limite:%d/%m à %H:%M}"
        notifier(db, "rappel_envois", titre, "/envois", corps=a.nom)
        alertes.telegram_pour(db, compte, "recap", f"{titre} : {a.nom}")
        n += 1
    alertes.valider(db)
    return n


dressing.APRES_SYNCHRO.append(ventes_disparues)
