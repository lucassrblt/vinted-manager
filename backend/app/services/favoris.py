"""Favoris : message et offre au membre qui vient de mettre une annonce en favori (section 9).

Les notifications Vinted sont lues par l'extension (événement « notifications ») ; leur format exact
n'a pas été capturé : l'extraction est volontairement tolérante (texte « favori », identifiants de
l'annonce et du membre dans les champs ou les liens). Une notification inexploitable est journalisée
et signalée une fois par jour, jamais devinée.
"""

import random
import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Article, CompteVinted, ConversationVinted, FavoriVinted, TacheVinted
from app.models.enums import StatutArticle
from app.services import alertes, brouillons, file_vinted, horaires, offres, reglages, taches
from app.services.marques import normaliser

AGE_MAX = timedelta(hours=12)  # un favori de la nuit est traité à 8 h s'il a moins de 12 h
VUES_MAX = 300
BALISES = re.compile(r"<[^>]+>")
MOTIFS_ARTICLE = (re.compile(r"/items?/(\d{5,})"), re.compile(r"item_id=(\d{5,})"))
MOTIFS_MEMBRE = (re.compile(r"/member(?:s)?/(\d{3,})"), re.compile(r"(?:user|member|receiver)_id=(\d{3,})"))


def _texte(n: dict[str, Any]) -> str:
    morceaux = [str(n.get(k) or "") for k in ("body", "title", "subtitle", "text", "message")]
    return BALISES.sub(" ", " ".join(morceaux)).strip()


def _liens(n: dict[str, Any]) -> str:
    return " ".join(str(n.get(k) or "") for k in ("link", "url", "path", "deeplink", "action_url"))


def _premier(motifs: tuple[re.Pattern[str], ...], texte: str) -> int | None:
    for m in motifs:
        trouve = m.search(texte)
        if trouve:
            return int(trouve.group(1))
    return None


def _entier(v: Any) -> int | None:
    try:
        return int(str(v)) if v not in (None, "") else None
    except ValueError:
        return None


def est_favori(n: dict[str, Any]) -> bool:
    return "favori" in normaliser(_texte(n))


def extraire(n: dict[str, Any], soi: int | None) -> tuple[int | None, int | None, str | None]:
    """(annonce, membre, pseudo) d'une notification de favori ; None quand l'information manque."""
    liens = _liens(n)
    item = _premier(MOTIFS_ARTICLE, liens)
    if item is None and str(n.get("subject_type") or "").lower() in ("item", "items"):
        item = _entier(n.get("subject_id"))
    if item is None:
        item = _entier(n.get("item_id"))
    membre = _premier(MOTIFS_MEMBRE, liens)
    for cle in ("sender_id", "actor_id", "user_id"):
        if membre is None or membre == soi:
            membre = _entier(n.get(cle))
    if membre == soi:
        membre = None
    texte = _texte(n)
    pseudo = None
    m = re.match(r"\s*([\w.\-]{2,40})\s+(a |aime|vient)", texte)
    if m:
        pseudo = m.group(1)
    for cle in ("sender_login", "user_login", "login"):
        if not pseudo and n.get(cle):
            pseudo = str(n[cle])[:120]
    return item, membre, pseudo


def _date(n: dict[str, Any]) -> datetime | None:
    for cle in ("created_at", "updated_at", "time", "date"):
        d = horaires.date_vinted(n.get(cle))
        if d is not None:
            return d
    return None


def liste(donnees: dict[str, Any]) -> list[dict[str, Any]]:
    for cle in ("notifications", "items", "data"):
        v = donnees.get(cle)
        if isinstance(v, list):
            return [n for n in v if isinstance(n, dict)]
    return []


def notifications(db: Session, compte: CompteVinted, donnees: dict[str, Any]) -> dict[str, Any]:
    source = donnees.get("source")
    if source:
        alertes.journaliser(db, compte, "notifications", f"Liste des notifications lue via {source}.")
    lues = liste(donnees)
    premiere = compte.notifications_vues is None
    vues = list(compte.notifications_vues or [])
    nouveaux = inexploitables = 0
    for n in lues:
        nid = str(n.get("id") or "")
        if not nid or nid in vues:
            continue
        vues.append(nid)
        if premiere or not est_favori(n):
            continue  # première lecture : rien d'antérieur n'est relancé
        item, membre, pseudo = extraire(n, compte.vinted_user_id)
        if item is None or membre is None:
            inexploitables += 1
            continue
        if enregistrer(db, compte, item, membre, pseudo, _date(n) or horaires.maintenant(), nid):
            nouveaux += 1
    compte.notifications_vues = vues[-VUES_MAX:]
    if inexploitables:
        _signaler_format(db, compte, inexploitables)
    db.flush()
    return {"favoris": nouveaux, "inexploitables": inexploitables}


def _signaler_format(db: Session, compte: CompteVinted, n: int) -> None:
    alertes.journaliser(
        db,
        compte,
        "notifications",
        f"{n} notification(s) de favori sans annonce ou membre lisible.",
        "erreur",
    )
    maintenant = horaires.maintenant()
    if (
        compte.notifications_format_alerte_le
        and maintenant - compte.notifications_format_alerte_le < timedelta(days=1)
    ):
        return
    compte.notifications_format_alerte_le = maintenant
    alertes.alerter(
        db, compte, "tache_erreur", "Favoris non exploitables",
        "Le format des notifications Vinted n'est pas celui attendu : aucune relance n'est envoyée. "
        "Capture la liste des notifications (DevTools → Réseau) pour l'ajuster.",
    )  # fmt: skip


def enregistrer(
    db: Session,
    compte: CompteVinted,
    item_id: int,
    membre_id: int,
    pseudo: str | None,
    recu_le: datetime,
    nid: str | None,
) -> bool:
    """Enregistre le favori (une fois par membre et par annonce) et programme la relance si elle est possible."""
    deja = db.scalar(
        select(FavoriVinted.id).where(
            FavoriVinted.compte_id == compte.id,
            FavoriVinted.vinted_item_id == item_id,
            FavoriVinted.membre_id == membre_id,
        )
    )
    if deja:
        return False
    article = db.scalar(
        select(Article).where(Article.vinted_item_id == item_id, Article.compte_id == compte.id)
    )
    favori = FavoriVinted(
        compte_id=compte.id,
        article_id=article.id if article else None,
        vinted_item_id=item_id,
        membre_id=membre_id,
        membre_login=(pseudo or "")[:120] or None,
        notification_id=nid,
        recu_le=recu_le,
        created_at=horaires.maintenant(),
    )
    try:
        with db.begin_nested():
            db.add(favori)
    except IntegrityError:
        return False
    programmer(db, compte, favori, article)
    return True


def montant_offre(article: Article, reduction_pct: float, plancher_pct: float) -> Decimal | None:
    """Prix affiché moins la réduction, arrondi aux 50 centimes, jamais sous le plancher ; None si aucune
    réduction n'est possible."""
    if article.prix_vente_cible is None:
        return None
    affiche = article.prix_vente_cible
    plancher = offres.plancher_vinted(article.prix_initial or affiche, plancher_pct)
    montant = max(plancher, offres.arrondi_50(affiche * (1 - Decimal(str(reduction_pct)) / 100)))
    return montant if montant < affiche else None


def message(modele: str, pseudo: str | None, article: Article, montant: Decimal) -> str:
    texte = modele.replace("{article}", article.titre_annonce or article.nom).replace(
        "{prix}", offres.euros(montant)
    )
    # Sans pseudo, la formule reste naturelle : « Hello {prenom}, » → « Hello, ».
    texte = texte.replace("{prenom}", pseudo) if pseudo else re.sub(r"\s*\{prenom\}", "", texte)
    return re.sub(r"\s+([,.])", r"\1", re.sub(r"[ \t]{2,}", " ", texte)).strip()  # espace avant « ! ? » gardé


def programmer(db: Session, compte: CompteVinted, favori: FavoriVinted, article: Article | None) -> None:
    r = reglages.du_compte(compte)

    def ignorer(raison: str) -> None:
        favori.statut, favori.raison = "ignore", raison

    if not reglages.module_actif(compte, "favoris"):
        return ignorer("Module favoris coupé.")
    if article is None:
        return ignorer("Annonce non rattachée à un article.")
    if article.statut != StatutArticle.EN_LIGNE:
        return ignorer("Article plus en ligne.")
    montant = montant_offre(article, r["favoris"]["reduction_pct"], r["prix"]["plancher_pct"])
    if montant is None:
        return ignorer("Aucune réduction possible au-dessus du plancher.")
    maintenant = horaires.maintenant()
    f = r["favoris"]
    if horaires.actif(compte):
        quand = maintenant + horaires.delai(f["delai_min_s"], f["delai_max_s"])
    else:  # nuit : à l'ouverture, étalé, si le favori a encore moins de 12 h
        quand = horaires.prochaine_ouverture(compte) + horaires.delai(f["delai_min_s"], 15 * 60)
    if quand - favori.recu_le > AGE_MAX:
        return ignorer("Favori trop ancien (plus de 12 h).")
    texte = message(random.choice(f["messages"]), favori.membre_login, article, montant)
    tache = taches.creer(
        db,
        compte,
        "relance_favori",
        {
            "item_id": favori.vinted_item_id,
            "membre_id": favori.membre_id,
            "login": favori.membre_login,
            "texte": texte,
            "montant": brouillons.prix_texte(montant),
            "article": article.nom,
            "favori_id": favori.id,
        },
        article.id,
        quand,
        cle=f"favori:{favori.vinted_item_id}:{favori.membre_id}",
    )
    favori.statut, favori.tache_id, favori.montant_offre = "programme", tache.id, montant


@file_vinted.apres("relance_favori")
def _apres_relance(db: Session, compte: CompteVinted, tache: TacheVinted, ok: bool) -> None:
    favori = db.get(FavoriVinted, tache.payload.get("favori_id")) if tache.payload.get("favori_id") else None
    r = tache.resultat or {}
    if favori is not None:
        favori.statut = "relance" if ok else "erreur"
        favori.offre_envoyee = bool(ok or r.get("offre_envoyee"))
        favori.raison = None if ok else tache.erreur
    conv_id = r.get("conversation_id")
    if ok and conv_id:
        # La négociation qui suivra repartira de l'offre envoyée.
        conv = db.get(ConversationVinted, str(conv_id))
        if conv is None:
            conv = ConversationVinted(
                id=str(conv_id), compte_id=compte.id, messages_vus=[], created_at=horaires.maintenant()
            )
            db.add(conv)
        conv.article_id = tache.article_id
        conv.vinted_item_ids = [int(tache.payload["item_id"])]
        conv.transaction_id = int(r["transaction_id"]) if r.get("transaction_id") else conv.transaction_id
        conv.interlocuteur_id = int(tache.payload["membre_id"])
        conv.interlocuteur_login = tache.payload.get("login")
        conv.dernier_propose = Decimal(str(tache.payload["montant"]))
        conv.dernier_message_le = horaires.maintenant()
    if not ok:
        alertes.alerter(
            db,
            compte,
            "tache_erreur",
            "Relance d'un favori en échec",
            tache.erreur or "",
            article_id=tache.article_id,
        )


file_vinted.EVENEMENTS["notifications"] = notifications


def relancer_avant_republication(db: Session, compte: CompteVinted, article: Article) -> int:
    """Avant la republication : une offre aux membres qui ont mis l'annonce en favori et n'en ont pas reçu.
    Seule source : l'historique des favoris enregistré ici (aucun autre appel à Vinted)."""
    r = reglages.du_compte(compte)
    montant = montant_offre(article, r["favoris"]["reduction_pct"], r["prix"]["plancher_pct"])
    if montant is None or article.vinted_item_id is None:
        return 0
    n = 0
    for f in db.scalars(
        select(FavoriVinted).where(
            FavoriVinted.compte_id == compte.id,
            FavoriVinted.vinted_item_id == article.vinted_item_id,
            FavoriVinted.offre_envoyee.is_(False),
            FavoriVinted.statut.in_(("a_relancer", "ignore", "erreur")),
        )
    ):
        texte = message(random.choice(r["favoris"]["messages"]), f.membre_login, article, montant)
        tache = taches.creer(
            db, compte, "relance_favori",
            {"item_id": f.vinted_item_id, "membre_id": f.membre_id, "login": f.membre_login, "texte": texte,
             "montant": brouillons.prix_texte(montant), "article": article.nom, "favori_id": f.id, "avant_republication": True},
            article.id, horaires.maintenant() + horaires.delai(r["favoris"]["delai_min_s"], 10 * 60),
            cle=f"favori-republication:{f.vinted_item_id}:{f.membre_id}",
        )  # fmt: skip
        if tache.statut == "a_faire":
            f.statut, f.tache_id, f.montant_offre = "programme", tache.id, montant
            n += 1
    return n
