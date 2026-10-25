"""Assistant Vinted : messages et offres reçus, lus par l'extension, traités par le backend (section 8).

1. Événement « inbox » (première page de la messagerie) : on répond la liste des conversations à lire,
   celles dont le dernier message est plus récent que le point de reprise et ne vient pas du compte.
2. Événement « conversation » : chaque message nouveau est traité une seule fois.
   - Offre reçue : règles déterministes de `offres.decider_vinted` (jamais l'IA).
   - Message : réponse rédigée par l'IA à partir de la fiche seulement ; escalade sur Telegram en cas de
     doute (mesures absentes, paiement ou contact hors Vinted, litige, lot, message suspect).
   La tâche part 20 à 60 s plus tard en journée, 5 à 15 min la nuit.
"""

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging import log
from app.models import Article, CompteVinted, ConversationVinted, TacheVinted
from app.services import alertes, brouillons, file_vinted, horaires, ia, offres, reglages, taches, telegram

LECTURES_MAX = 5  # conversations lues par passage (les autres le seront au suivant)
VUS_MAX = 100
STATUTS_OFFRE_TERMINEE = {20, 30}  # acceptée, refusée
TYPES_TEXTE = {"legacy_reply", "reply_plain", "reply"}
TYPES_OFFRE = {"legacy_offer_request"}
REFUS_PAR_DEFAUT = (
    "Bonjour, merci pour ton offre, mais je ne peux pas descendre autant sur cet article. Belle journée !"
)

# Filet de sécurité : ces sujets passent toujours par Lucas, quoi qu'en dise l'IA.
ESCALADES: list[tuple[str, re.Pattern[str]]] = [
    (
        "paiement ou contact hors Vinted",
        re.compile(
            r"paypal|virement|lydia|\biban\b|wero|western|hors (de )?vinted|en dehors de vinted|main propre|"
            r"whats ?app|t[ée]l[ée]phone|\bnum[ée]ro\b|\b0[67](\s?\d{2}){4}\b|@[\w-]+\.\w+|\bmail\b|insta|snap",
            re.I,
        ),
    ),
    (
        "litige ou retour",
        re.compile(r"litige|rembours|arnaque|pas re[çc]u|ab[iî]m[ée]|cass[ée]|\bretour", re.I),
    ),
    (
        "lot de plusieurs articles",
        re.compile(r"\blot\b|plusieurs articles|les deux|les trois|ensemble", re.I),
    ),
]
MESURES = re.compile(r"mesure|longueur|largeur|aisselle|\bcm\b|tour de (taille|poitrine)|\bdimension", re.I)


# --- Lecture de la messagerie ----------------------------------------------------------------


def _id_user(valeur: Any) -> int | None:
    try:
        return int(str(valeur))
    except (TypeError, ValueError):
        return None


def _conversation(db: Session, compte: CompteVinted, conv_id: str) -> ConversationVinted:
    conv = db.get(ConversationVinted, conv_id)
    if conv is None:
        conv = ConversationVinted(
            id=conv_id, compte_id=compte.id, messages_vus=[], created_at=horaires.maintenant()
        )
        db.add(conv)
    elif conv.compte_id != compte.id:
        raise ValueError("conversation d'un autre compte")
    return conv


def _interlocuteur(conv: ConversationVinted, donnees: dict[str, Any]) -> None:
    for u in donnees.get("opposite_users") or []:
        d = (u or {}).get("data") or {}
        if d.get("id") is not None:
            conv.interlocuteur_id = _id_user(d["id"])
            conv.interlocuteur_login = str(d.get("login_name") or "")[:120] or conv.interlocuteur_login
            return


def _rattacher_article(
    db: Session, compte: CompteVinted, conv: ConversationVinted, item_ids: list[int]
) -> None:
    if item_ids:
        conv.vinted_item_ids = item_ids
    if conv.article_id is None and conv.vinted_item_ids:
        conv.article_id = db.scalar(
            select(Article.id).where(
                Article.vinted_item_id == conv.vinted_item_ids[0], Article.compte_id == compte.id
            )
        )


def inbox(db: Session, compte: CompteVinted, donnees: dict[str, Any]) -> dict[str, Any]:
    maintenant = horaires.maintenant()
    soi = compte.vinted_user_id
    premiere = compte.inbox_initialise_le is None
    if premiere:
        compte.inbox_initialise_le = maintenant  # rien d'antérieur ne sera traité
    a_lire: list[str] = []
    for c in donnees.get("conversations") or []:
        if not isinstance(c, dict) or not c.get("id"):
            continue
        try:
            conv = _conversation(db, compte, str(c["id"]))
        except ValueError:
            continue
        _interlocuteur(conv, c)
        items = [_id_user(i.get("id")) for i in (c.get("data") or {}).get("inventory_items") or []]
        _rattacher_article(db, compte, conv, [i for i in items if i])
        dernier = c.get("last_message") or {}
        date = horaires.date_vinted(dernier.get("created_at"))
        if date is None:
            continue
        if conv.dernier_message_le is None or date > conv.dernier_message_le:
            conv.dernier_message_le = date
        if premiere:
            conv.dernier_traite_le = max(conv.dernier_traite_le or date, date)
            continue
        if conv.dernier_traite_le is not None and date <= conv.dernier_traite_le:
            continue
        if soi is not None and _id_user(dernier.get("sender_id")) == soi:
            # Réponse faite depuis Vinted (par Lucas ou l'extension) : plus rien à faire dans cette conversation.
            conv.dernier_traite_le = date
            taches.annuler(db, compte, "repondre_message", conversation_id=conv.id)
            continue
        if compte.inbox_initialise_le is not None and date <= compte.inbox_initialise_le:
            continue
        a_lire.append(conv.id)
    db.flush()
    return {"a_lire": a_lire[:LECTURES_MAX]}


# --- Traitement d'une conversation ------------------------------------------------------------


def _montant(v: Any) -> Decimal | None:
    brut = v.get("amount") if isinstance(v, dict) else v
    try:
        return Decimal(str(brut).replace(",", ".")).quantize(Decimal("0.01")) if brut is not None else None
    except InvalidOperation:
        return None


def _texte(message: dict[str, Any]) -> str:
    data = message.get("data") or {}
    entite = data.get("entity") or {}
    return str(entite.get("body") or data.get("content") or "").strip()


def conversation(db: Session, compte: CompteVinted, donnees: dict[str, Any]) -> dict[str, Any]:
    conv_id = str(donnees.get("id") or "")
    if not conv_id:
        return {"traite": 0}
    try:
        conv = _conversation(db, compte, conv_id)
    except ValueError:
        return {"traite": 0}
    data = donnees.get("data") or {}
    _interlocuteur(conv, donnees)
    items = [_id_user(i.get("inventory_item_id")) for i in data.get("items") or [] if isinstance(i, dict)]
    _rattacher_article(db, compte, conv, [i for i in items if i])
    conv.transaction_id = _id_user(data.get("transaction_id")) or conv.transaction_id
    soi = compte.vinted_user_id
    vus = list(conv.messages_vus or [])
    bornes = [d for d in (conv.dernier_traite_le, compte.inbox_initialise_le) if d is not None]
    limite = max(bornes) if bornes else None
    nouveaux: list[tuple[datetime, dict[str, Any]]] = []
    for m in donnees.get("messages") or []:
        if not isinstance(m, dict):
            continue
        date = horaires.date_vinted(m.get("created_at"))
        if date is None:
            continue
        if conv.dernier_message_le is None or date > conv.dernier_message_le:
            conv.dernier_message_le = date
        mid = str(m.get("id") or "")
        expediteur = _id_user(m.get("sender_id"))
        if mid in vus or (limite is not None and date <= limite) or expediteur in (soi, 0, None):
            continue
        nouveaux.append((date, m))
    nouveaux.sort(key=lambda x: x[0])
    if not nouveaux:
        return {"traite": 0}
    conv.messages_vus = (vus + [str(m.get("id")) for _, m in nouveaux])[-VUS_MAX:]
    conv.dernier_traite_le = nouveaux[-1][0]
    offres_recues = [m for _, m in nouveaux if m.get("message_type") in TYPES_OFFRE]
    textes = [_texte(m) for _, m in nouveaux if m.get("message_type") in TYPES_TEXTE and _texte(m)]
    article = db.get(Article, conv.article_id) if conv.article_id else None
    if offres_recues:
        _offre(db, compte, conv, article, offres_recues[-1])
    elif textes:
        _messages(db, compte, conv, article, textes, nouveaux[-1][1])
    db.flush()
    return {"traite": len(nouveaux)}


def _executer_apres(compte: CompteVinted) -> datetime:
    return horaires.maintenant() + horaires.delai_reponse(compte)


def _fiche(article: Article) -> dict[str, Any]:
    return {
        "nom": article.nom, "marque": article.marque, "modele": article.modele, "categorie": article.categorie,
        "taille": article.taille, "couleur": article.couleur, "etat": article.etat, "matiere": article.matiere,
        "defauts": article.defauts, "mesures": article.mesures,
    }  # fmt: skip


def _offre(
    db: Session,
    compte: CompteVinted,
    conv: ConversationVinted,
    article: Article | None,
    message: dict[str, Any],
) -> None:
    entite = (message.get("data") or {}).get("entity") or {}
    statut = entite.get("status")
    if statut in STATUTS_OFFRE_TERMINEE or entite.get("current") is False:
        return  # déjà acceptée, refusée ou remplacée
    offre = _montant(entite.get("price"))
    demande = entite.get("offer_request_id")
    transaction = entite.get("transaction_id") or conv.transaction_id
    if offre is None or demande is None or transaction is None:
        alertes.alerter(
            db,
            compte,
            "offre_hors_regles",
            "Offre illisible",
            f"Conversation {conv.id} : à traiter sur Vinted.",
        )
        return
    base = {"conversation_id": conv.id, "transaction_id": int(transaction), "offer_request_id": int(demande)}
    appliquer_regles(
        db, compte, conv, article, offre, base, f"offre:{demande}", message_acheteur=f"Offre de {offre} €"
    )


def appliquer_regles(
    db: Session,
    compte: CompteVinted,
    conv: ConversationVinted,
    article: Article | None,
    offre: Decimal,
    base: dict[str, Any],
    cle: str,
    message_acheteur: str,
    offre_texte: bool = False,
) -> None:
    """Décision déterministe sur une offre (Vinted ou formulée dans un message) et tâche correspondante."""
    titre = article.nom if article else "article inconnu"
    if article is None or article.prix_vente_cible is None:
        alertes.alerter(
            db, compte, "offre_hors_regles", "Offre sur un article inconnu",
            f"{offre} € de {conv.interlocuteur_login or 'un membre'} : article non rattaché, à traiter sur Vinted.",
        )  # fmt: skip
        return
    r = reglages.du_compte(compte)
    decision = offres.decider_vinted(
        offre,
        article.prix_vente_cible,
        article.prix_initial,
        conv.dernier_propose,
        conv.plancher_renvoye,
        r["assistant"]["seuil_acceptation_pct"],
        r["assistant"]["seuil_refus_pct"],
        r["prix"]["plancher_pct"],
    )
    alertes.journaliser(db, compte, "assistant", f"{titre} : {decision.explication}", article_id=article.id)
    commun = {**base, "conversation_id": conv.id, "article": titre, "offre": brouillons.prix_texte(offre)}
    if decision.action == "accepter":
        if offre_texte:  # pas de demande d'offre Vinted à accepter : on envoie une offre vendeur à ce montant
            taches.creer(
                db,
                compte,
                "contre_offre",
                commun | {"montant": brouillons.prix_texte(offre)},
                article.id,
                _executer_apres(compte),
                cle,
            )
        else:
            taches.creer(
                db,
                compte,
                "accepter_offre",
                commun | {"montant": brouillons.prix_texte(offre)},
                article.id,
                _executer_apres(compte),
                cle,
            )
    elif decision.action == "contre":
        assert decision.montant is not None
        taches.creer(
            db, compte, "contre_offre",
            commun | {"montant": brouillons.prix_texte(decision.montant), "renvoi_plancher": decision.renvoi_plancher},
            article.id, _executer_apres(compte), cle,
        )  # fmt: skip
    elif decision.action == "refuser":
        texte = _texte_refus(message_acheteur, article, decision)
        type_tache = "repondre_message" if offre_texte else "refuser_offre"
        taches.creer(
            db, compte, type_tache, commun | {"texte": texte}, article.id, _executer_apres(compte), cle
        )
    else:  # escalade : Lucas décide (accepter quand même, ou ignorer)
        if offre_texte:
            alertes.alerter(
                db, compte, "offre_hors_regles", "Offre sous le plancher", f"{titre} : {decision.explication}"
            )
            return
        tache = taches.creer(
            db, compte, "accepter_offre",
            commun | {"montant": brouillons.prix_texte(offre), "raison_escalade": decision.explication},
            article.id, cle=cle, statut="a_valider",
        )  # fmt: skip
        alertes.alerter(
            db, compte, "offre_hors_regles", "Offre à décider",
            f"{titre} : {decision.explication} Accepter {offre} € ?",
            article_id=article.id, boutons=telegram.boutons_tache(tache.id, modifier=False),
        )  # fmt: skip


def _texte_refus(message: str, article: Article, decision: offres.DecisionVinted) -> str:
    try:
        texte = ia.suggerer_reponse(
            message,
            "offre",
            _fiche(article),
            {"decision": "refuser", "montant_offre": message, "montant_propose": None},
            [],
        )
        return texte or REFUS_PAR_DEFAUT
    except ia.ErreurIA as exc:
        log.info("assistant_refus_sans_ia", raison=str(exc))
        return REFUS_PAR_DEFAUT


def raison_escalade(textes: list[str], article: Article | None) -> str | None:
    """Escalades obligatoires détectées sans l'IA."""
    tout = " ".join(textes)
    for raison, motif in ESCALADES:
        if motif.search(tout):
            return f"Message à relire : {raison}."
    if MESURES.search(tout) and not (article and article.mesures):
        return "Message à relire : mesures demandées, absentes de la fiche."
    return None


def _messages(
    db: Session,
    compte: CompteVinted,
    conv: ConversationVinted,
    article: Article | None,
    textes: list[str],
    dernier: dict[str, Any],
) -> None:
    cle = f"msg:{dernier.get('id')}"
    base = {"conversation_id": conv.id, "article": article.nom if article else None}
    if len(conv.vinted_item_ids or []) > 1:
        _escalader(db, compte, conv, article, textes, "", "Demande sur plusieurs articles (lot).", cle)
        return
    if article is None:
        _escalader(
            db, compte, conv, article, textes, "", "Article non rattaché à une fiche de vinted-manager.", cle
        )
        return
    r = reglages.du_compte(compte)
    try:
        reponse = ia.repondre_acheteur(
            textes, _fiche(article), r["assistant"]["ton"], r["assistant"]["reponses_types"]
        )
    except ia.ErreurIA as exc:
        _escalader(db, compte, conv, article, textes, "", f"IA indisponible : {exc}", cle)
        return
    raison = raison_escalade(textes, article)
    if reponse.intention in ("lot", "suspect"):
        raison = raison or f"Message à relire ({reponse.intention})."
    if reponse.escalade:
        raison = raison or reponse.raison_escalade or "L'IA a un doute."
    if raison is None and reponse.intention == "offre_texte" and reponse.montant_propose:
        try:
            offre = Decimal(str(reponse.montant_propose)).quantize(Decimal("0.01"))
        except InvalidOperation:
            offre = None
        if offre is not None and offre > 0 and conv.transaction_id is not None:
            appliquer_regles(
                db, compte, conv, article, offre, base | {"transaction_id": conv.transaction_id}, cle,
                message_acheteur=textes[-1], offre_texte=True,
            )  # fmt: skip
            return
        raison = "Prix proposé dans un message, sans transaction Vinted pour répondre par une offre."
    if raison is not None:
        _escalader(db, compte, conv, article, textes, reponse.reponse, raison, cle)
        return
    if not reponse.reponse:
        return  # rien à dire (ex. simple remerciement sans réponse utile)
    taches.annuler(db, compte, "repondre_message", conversation_id=conv.id)
    taches.creer(
        db, compte, "repondre_message", base | {"texte": reponse.reponse, "intention": reponse.intention},
        article.id, _executer_apres(compte), cle,
    )  # fmt: skip


def _escalader(
    db: Session,
    compte: CompteVinted,
    conv: ConversationVinted,
    article: Article | None,
    textes: list[str],
    proposition: str,
    raison: str,
    cle: str,
) -> None:
    taches.annuler(db, compte, "repondre_message", conversation_id=conv.id)
    tache = taches.creer(
        db, compte, "repondre_message",
        {"conversation_id": conv.id, "texte": proposition, "raison_escalade": raison,
         "article": article.nom if article else None, "messages": textes[-5:]},
        article.id if article else None, cle=cle, statut="a_valider",
    )  # fmt: skip
    qui = conv.interlocuteur_login or "un acheteur"
    corps = f"{qui} ({article.nom if article else 'article inconnu'}) : « {textes[-1][:300]} »\n{raison}"
    if proposition:
        corps += f"\nRéponse proposée : « {proposition} »"
    alertes.alerter(
        db, compte, "intervention", "Intervention requise", corps, article_id=article.id if article else None,
        boutons=telegram.boutons_tache(tache.id, envoyer=bool(proposition)),
    )  # fmt: skip


# --- Résultats des tâches ---------------------------------------------------------------------


def _conv_de(db: Session, tache: TacheVinted) -> ConversationVinted | None:
    cid = tache.payload.get("conversation_id")
    return db.get(ConversationVinted, str(cid)) if cid else None


@file_vinted.apres("contre_offre")
def _apres_contre_offre(db: Session, compte: CompteVinted, tache: TacheVinted, ok: bool) -> None:
    conv = _conv_de(db, tache)
    if ok and conv is not None:
        conv.dernier_propose = Decimal(str(tache.payload["montant"]))
        if tache.payload.get("renvoi_plancher"):
            conv.plancher_renvoye = True
        conv.dernier_message_le = horaires.maintenant()
    elif not ok:
        alertes.alerter(
            db,
            compte,
            "tache_erreur",
            "Contre-offre non envoyée",
            tache.erreur or "",
            article_id=tache.article_id,
        )


def _apres_message(db: Session, compte: CompteVinted, tache: TacheVinted, ok: bool) -> None:
    conv = _conv_de(db, tache)
    if ok and conv is not None:
        conv.dernier_message_le = horaires.maintenant()
    elif not ok:
        alertes.alerter(
            db,
            compte,
            "tache_erreur",
            f"Échec : {tache.type.replace('_', ' ')}",
            tache.erreur or "",
            article_id=tache.article_id,
        )


for _type in ("repondre_message", "accepter_offre", "refuser_offre"):
    file_vinted.APRES[_type] = _apres_message

file_vinted.EVENEMENTS["inbox"] = inbox
file_vinted.EVENEMENTS["conversation"] = conversation
