"""Traitement d'un mail Vinted : enregistrement, classement, puis action selon son type.

Statut de traitement d'un mail :
- `traite` : l'action a été faite (vente créée, bordereau rattaché, statut mis à jour…)
- `nouveau` : type reconnu mais action en attente (vente à confirmer, bordereau ou livraison à rattacher)
- `a_classer` : aucune règle ne correspond
- `ignore` : écarté à la main
"""

import re
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.logging import log
from app.models import (
    Article,
    EmailVinted,
    Envoi,
    HistoriqueStatut,
    Message,
    Parametres,
    PieceJointe,
    RegleClassement,
    Vente,
)
from app.models.enums import (
    StatutArticle,
    StatutEnvoi,
    StatutMessage,
    StatutTraitementEmail,
    TypeEmail,
)
from app.services import classifieur, offres, rapprochement, stats, storage
from app.services.email_parser import MailLu, PieceJointeBrute, liens_html, re_liens
from app.services.marques import normaliser
from app.services.notifications import annuler_en_attente, envoyer_en_attente, notifier
from app.services.statuts import changer_statut

DELAI_ENVOI_JOURS_OUVRES = 5  # délai Vinted pour expédier après une vente
SEUIL_TITRE = 75.0
AGE_MAX_NOTIFICATION_JOURS = 2

# Statut d'article associé à chaque statut d'envoi.
ARTICLE_PAR_ENVOI = {StatutEnvoi.DEPOSE: StatutArticle.ENVOYE, StatutEnvoi.LIVRE: StatutArticle.LIVRE}


def regles_actives(db: Session) -> list[RegleClassement]:
    return list(db.scalars(select(RegleClassement).where(RegleClassement.active.is_(True))))


def _date(v: Any) -> datetime | None:
    return datetime.fromisoformat(v) if isinstance(v, str) else None


# --- Enregistrement ---------------------------------------------------------------------------


def enregistrer_mail(db: Session, mail: MailLu, compte_id: int | None = None) -> EmailVinted | None:
    """Enregistre, classe et traite un mail reçu sur la boîte du compte `compte_id`.
    Renvoie None s'il est déjà connu (Message-ID)."""
    if db.scalar(select(EmailVinted.id).where(EmailVinted.message_id == mail.message_id)):
        return None
    resultat = classifieur.classer(regles_actives(db), mail)
    email = EmailVinted(
        message_id=mail.message_id,
        compte_id=compte_id,
        date=mail.date or utcnow(),
        expediteur=mail.expediteur[:255],
        sujet=mail.sujet[:500],
        corps_texte=mail.texte_complet,
        corps_html=mail.html or None,
        type_detecte=resultat.type,
        regle_id=resultat.regle_id,
        donnees_extraites=resultat.donnees,
        statut_traitement=StatutTraitementEmail.A_CLASSER
        if resultat.type is None
        else StatutTraitementEmail.NOUVEAU,
    )
    db.add(email)
    db.flush()
    for pj in mail.pieces_jointes:
        chemin = storage.ecrire_fichier(f"emails/{email.id}", pj.nom, pj.contenu)
        db.add(PieceJointe(email_id=email.id, nom=pj.nom[:255], mime=pj.mime[:100], chemin=chemin))
    db.flush()
    if resultat.type:
        appliquer(db, email)
    else:
        # Filet de sécurité : un mail Vinted inconnu peut être une offre ou un message à ne pas rater.
        notifier(db, "non_classe", "Mail Vinted non reconnu", "/mails", corps=email.sujet or "")
    db.commit()
    if email.date and email.date < utcnow() - timedelta(days=AGE_MAX_NOTIFICATION_JOURS):
        annuler_en_attente(db)  # relecture de l'historique : pas de notification pour les vieux mails
    else:
        envoyer_en_attente(db)
    return email


def appliquer(db: Session, email: EmailVinted, article: Article | None = None) -> None:
    """Exécute l'action du type détecté. `article` force l'article concerné (rattachement manuel)."""
    actions = {
        TypeEmail.VENTE: _vente,
        TypeEmail.BORDEREAU: _bordereau,
        TypeEmail.EXPEDIE: _suivi_colis,
        TypeEmail.LIVRE: _suivi_colis,
        TypeEmail.LITIGE: _litige,
        TypeEmail.ANNULATION: _annulation,
        TypeEmail.MESSAGE: _message,
        TypeEmail.OFFRE: _message,
        TypeEmail.FAVORI: _favori,
    }
    action = actions.get(TypeEmail(email.type_detecte)) if email.type_detecte else None
    if action is None:
        email.statut_traitement = StatutTraitementEmail.TRAITE  # argent, évaluation, autre : rien à faire
        return
    action(db, email, article)


# --- Ventes -----------------------------------------------------------------------------------


def _vente(db: Session, email: EmailVinted, article: Article | None) -> None:
    d = email.donnees_extraites or {}
    if article is None:
        liste = rapprochement.candidats(
            db,
            d.get("titre_article"),
            _decimal(d.get("prix")),
            compte_id=email.compte_id,
            date_mail=email.date,
        )
        choix = rapprochement.choix_automatique(liste)
        if choix is None:
            email.statut_traitement = StatutTraitementEmail.NOUVEAU  # -> « Ventes à confirmer »
            corps = " · ".join(
                x
                for x in (d.get("titre_article"), _prix_texte(_decimal(d.get("prix"))), d.get("acheteur"))
                if x
            )
            notifier(db, "vente", "🛍️ Vente à confirmer", "/ventes", corps=corps, compte_id=email.compte_id)
            return
        article = db.get(Article, choix.article_id)
        assert article is not None
        confirmer_vente(db, email, article, auto=True)
    else:
        confirmer_vente(db, email, article, auto=False)


def _decimal(v: Any) -> Decimal | None:
    return Decimal(v) if isinstance(v, str) and v else None


def _prix_texte(v: Decimal | None) -> str:
    return offres.euros(v) if v is not None else ""


def confirmer_vente(db: Session, email: EmailVinted, article: Article, auto: bool) -> Vente:
    d = email.donnees_extraites or {}
    if article.statut in rapprochement.STATUTS_A_COMPLETER:
        vente = _completer_vente_importee(db, email, article, auto)
    else:
        vente = _nouvelle_vente(db, email, article, auto)
    if not article.titre_annonce and d.get("titre_article"):
        article.titre_annonce = str(d["titre_article"])[:120]  # titre Vinted : sert aux mails suivants
    rejouer_mails_de_la_vente(db, vente)
    return vente


def _nouvelle_vente(db: Session, email: EmailVinted, article: Article, auto: bool) -> Vente:
    d = email.donnees_extraites or {}
    quand = email.date or utcnow()
    prix = _decimal(d.get("prix")) or article.prix_vente_cible or Decimal("0")
    vente = Vente(
        article_id=article.id,
        prix=prix,
        date_heure=quand,
        numero_commande=d.get("numero_commande"),
        acheteur=d.get("acheteur"),
        email_id=email.id,
        auto_rapproche=auto,
    )
    db.add(vente)
    db.flush()
    article.prix_vente_reel = prix
    if article.compte_id is None:
        article.compte_id = email.compte_id  # l'article était donc en vente sur ce compte
    changer_statut(
        db,
        article,
        StatutArticle.VENDU,
        quand=quand,
        commentaire="Vente détectée (auto)" if auto else "Vente confirmée",
        forcer_date=True,
    )
    limite = _date(d.get("date_limite")) or classifieur.ajouter_jours_ouvres(quand, DELAI_ENVOI_JOURS_OUVRES)
    envoi = Envoi(vente_id=vente.id, date_limite_envoi=limite, statut=StatutEnvoi.A_IMPRIMER)
    db.add(envoi)
    db.flush()
    email.vente_id = vente.id
    email.article_id = article.id
    email.statut_traitement = StatutTraitementEmail.TRAITE
    # Le mail de vente peut contenir directement le bordereau.
    _rattacher_bordereau(db, envoi, email)
    corps = _prix_texte(prix) + (f" · acheté par {vente.acheteur}" if vente.acheteur else "")
    notifier(
        db,
        "vente",
        f"🛍️ Vendu : {article.nom}",
        f"/stock/{article.id}",
        corps=corps,
        compte_id=article.compte_id or email.compte_id,
    )
    return vente


def _dater_passage_vendu(db: Session, article: Article, quand: datetime, commentaire: str) -> None:
    passage = db.scalar(
        select(HistoriqueStatut)
        .where(
            HistoriqueStatut.article_id == article.id, HistoriqueStatut.nouveau_statut == StatutArticle.VENDU
        )
        .order_by(HistoriqueStatut.date.desc())
    )
    if passage is not None:
        passage.date = quand
        passage.commentaire = commentaire


def _completer_vente_importee(db: Session, email: EmailVinted, article: Article, auto: bool) -> Vente:
    """Article déjà vendu à l'import (date estimée) : le mail donne la vraie date, le prix et l'acheteur.
    Le statut ne change pas ; les mails d'expédition et de livraison qui suivent mettent l'envoi à jour."""
    d = email.donnees_extraites or {}
    quand = email.date or utcnow()
    prix = _decimal(d.get("prix")) or article.prix_vente_reel or article.prix_vente_cible or Decimal("0")
    vente = Vente(
        article_id=article.id,
        prix=prix,
        date_heure=quand,
        numero_commande=d.get("numero_commande"),
        acheteur=d.get("acheteur"),
        email_id=email.id,
        auto_rapproche=auto,
        date_estimee_import=article.date_vente or quand,
    )
    db.add(vente)
    db.flush()
    ancienne = article.date_vente
    article.date_vente = quand
    article.prix_vente_reel = prix
    if article.compte_id is None:
        article.compte_id = email.compte_id
    _dater_passage_vendu(db, article, quand, "Date de vente corrigée d'après le mail Vinted")
    log.info("vente_completee", article=article.id, ancienne_date=str(ancienne), date=str(quand))
    statut_envoi = {
        StatutArticle.ENVOYE: StatutEnvoi.DEPOSE,
        StatutArticle.LIVRE: StatutEnvoi.LIVRE,
    }.get(StatutArticle(article.statut), StatutEnvoi.A_IMPRIMER)
    limite = _date(d.get("date_limite")) or classifieur.ajouter_jours_ouvres(quand, DELAI_ENVOI_JOURS_OUVRES)
    envoi = Envoi(vente_id=vente.id, date_limite_envoi=limite, statut=statut_envoi)
    db.add(envoi)
    db.flush()
    email.vente_id = vente.id
    email.article_id = article.id
    email.statut_traitement = StatutTraitementEmail.TRAITE
    _rattacher_bordereau(db, envoi, email)
    return vente


def annuler_vente(db: Session, vente: Vente, commentaire: str = "Rapprochement annulé") -> None:
    """Annule un rapprochement : l'article repasse en ligne et le mail revient « à confirmer »."""
    article = db.get(Article, vente.article_id)
    if article is not None and vente.date_estimee_import is not None:
        # Vente importée : l'article reste vendu, avec sa date estimée d'origine.
        article.date_vente = vente.date_estimee_import
        _dater_passage_vendu(db, article, vente.date_estimee_import, "Import Excel (date estimée)")
    elif article is not None:
        changer_statut(db, article, StatutArticle.EN_LIGNE, commentaire=commentaire)
        article.date_vente = None
        article.prix_vente_reel = None
        article.date_envoi = None
    for email in db.scalars(select(EmailVinted).where(EmailVinted.vente_id == vente.id)):
        email.vente_id = None
        email.article_id = None
        if email.type_detecte == TypeEmail.VENTE:
            email.statut_traitement = StatutTraitementEmail.NOUVEAU
    db.delete(vente)  # l'envoi est supprimé en cascade
    db.flush()


# --- Envois -----------------------------------------------------------------------------------


def _rattacher_bordereau(db: Session, envoi: Envoi, email: EmailVinted) -> bool:
    d = email.donnees_extraites or {}
    pdf = db.scalar(
        select(PieceJointe).where(PieceJointe.email_id == email.id, PieceJointe.mime == "application/pdf")
    )
    if pdf is None and not d.get("lien_bordereau"):
        return False
    if pdf is not None:
        envoi.fichier_bordereau = pdf.chemin
    if d.get("lien_bordereau"):
        envoi.lien_bordereau = d["lien_bordereau"]
    if d.get("date_limite"):
        envoi.date_limite_envoi = _date(d["date_limite"])
    return True


def titre_cle(titre: str | None) -> str:
    """Titre comparable : sans accents, ponctuation ni espaces multiples."""
    return " ".join(re.sub(r"[^\w\s]", " ", normaliser(titre or "")).split())


def titres_du_mail(titre: str | None) -> list[str]:
    """Le titre entier, puis chaque article d'un lot (« A, B » dans un bordereau groupé)."""
    if not titre:
        return []
    morceaux = [titre_cle(t) for t in re.split(r",\s+", titre)] if "," in titre else []
    return [titre_cle(titre)] + [m for m in morceaux if m]


def titre_vente(db: Session, vente: Vente) -> str:
    """Titre de l'annonce Vinted vendue : celui du mail de vente, sinon le titre d'annonce de l'article."""
    if titre := _titre_mail_vente(db, vente):
        return titre_cle(titre)
    article = db.get(Article, vente.article_id)
    return titre_cle(article.titre_annonce or article.nom) if article else ""


def trouver_envoi(
    db: Session,
    donnees: dict[str, Any],
    statuts_ouverts: bool = True,
    date_mail: datetime | None = None,
    sans_bordereau: bool = False,
) -> Envoi | None:
    """Envoi concerné par un mail : par numéro de commande, puis par titre exact de l'annonce vendue
    (la plus ancienne vente encore ouverte si le même titre a été vendu plusieurs fois), puis par
    ressemblance avec le nom de l'article."""
    requete = select(Envoi, Vente, Article).join(Vente, Envoi.vente_id == Vente.id).join(Article)
    if statuts_ouverts:
        requete = requete.where(Envoi.statut != StatutEnvoi.LIVRE)
    if date_mail is not None:
        requete = requete.where(Vente.date_heure <= date_mail)
    lignes = db.execute(requete.order_by(Vente.date_heure)).all()
    if numero := donnees.get("numero_commande"):
        for envoi, vente, _ in lignes:
            if vente.numero_commande and vente.numero_commande == numero:
                return envoi
    titres = titres_du_mail(donnees.get("titre_article"))
    if titres:
        exacts = [(e, v) for e, v, _ in lignes if titre_vente(db, v) in titres]
        if sans_bordereau:
            exacts = [x for x in exacts if not x[0].fichier_bordereau and not x[0].lien_bordereau] or exacts
        if (acheteur := donnees.get("acheteur")) and len(exacts) > 1:
            # Même titre vendu plusieurs fois : le pseudo de l'acheteur départage.
            exacts = [x for x in exacts if (x[1].acheteur or "").lower() == str(acheteur).lower()] or exacts
        if exacts:
            return exacts[0][0]
        # Repli prudent sur le nom de l'article : seulement les ventes dont on ne connaît pas le titre
        # Vinted, et une correspondance nette (sinon « Ralph Lauren » relierait n'importe quel article).
        sans_titre = [(e, a) for e, v, a in lignes if not _titre_mail_vente(db, v)]
        scores = sorted(
            ((rapprochement.score_titre(donnees["titre_article"], a), e) for e, a in sans_titre),
            key=lambda x: x[0],
            reverse=True,
        )
        if (
            scores
            and scores[0][0] >= rapprochement.SEUIL_AUTO
            and (len(scores) == 1 or scores[0][0] - scores[1][0] >= rapprochement.ECART_AUTO)
        ):
            return scores[0][1]
    return None


def _titre_mail_vente(db: Session, vente: Vente) -> str | None:
    mail = db.get(EmailVinted, vente.email_id) if vente.email_id else None
    titre = (mail.donnees_extraites or {}).get("titre_article") if mail else None
    return str(titre) if titre else None


def _envoi_de_article(db: Session, article: Article) -> Envoi | None:
    return db.scalar(
        select(Envoi).join(Vente).where(Vente.article_id == article.id).order_by(Vente.date_heure.desc())
    )


def _bordereau(db: Session, email: EmailVinted, article: Article | None) -> None:
    d = email.donnees_extraites or {}
    envoi = (
        _envoi_de_article(db, article)
        if article
        else trouver_envoi(db, d, date_mail=email.date, sans_bordereau=True)
    )
    if envoi is None:
        # Un seul colis sans bordereau en attente : c'est forcément lui.
        sans = db.scalars(
            select(Envoi).where(
                Envoi.fichier_bordereau.is_(None),
                Envoi.lien_bordereau.is_(None),
                Envoi.statut == StatutEnvoi.A_IMPRIMER,
            )
        ).all()
        envoi = sans[0] if len(sans) == 1 else None
    if envoi is None or not _rattacher_bordereau(db, envoi, email):
        email.statut_traitement = StatutTraitementEmail.NOUVEAU  # -> « à rattacher »
        return
    vente = db.get(Vente, envoi.vente_id)
    email.vente_id = envoi.vente_id
    email.article_id = vente.article_id if vente else None
    email.statut_traitement = StatutTraitementEmail.TRAITE


def changer_statut_envoi(
    db: Session, envoi: Envoi, statut: StatutEnvoi, quand: datetime | None = None
) -> None:
    """Met à jour l'envoi et l'article lié (déposé -> article envoyé, livré -> article livré)."""
    quand = quand or utcnow()
    envoi.statut = statut
    if statut in (StatutEnvoi.DEPOSE, StatutEnvoi.LIVRE) and envoi.date_depot is None:
        envoi.date_depot = quand
    vente = db.get(Vente, envoi.vente_id)
    article = db.get(Article, vente.article_id) if vente else None
    if article is None:
        return
    cible = ARTICLE_PAR_ENVOI.get(statut)
    if cible and article.statut != StatutArticle.LITIGE:
        if cible == StatutArticle.LIVRE and article.statut == StatutArticle.VENDU:
            changer_statut(db, article, StatutArticle.ENVOYE, quand=envoi.date_depot or quand)
        changer_statut(db, article, cible, quand=quand)


def _suivi_colis(db: Session, email: EmailVinted, article: Article | None) -> None:
    d = email.donnees_extraites or {}
    envoi = _envoi_de_article(db, article) if article else trouver_envoi(db, d, date_mail=email.date)
    if envoi is None:
        email.statut_traitement = StatutTraitementEmail.NOUVEAU
        return
    statut = StatutEnvoi.LIVRE if email.type_detecte == TypeEmail.LIVRE else StatutEnvoi.DEPOSE
    if not (statut == StatutEnvoi.DEPOSE and envoi.statut == StatutEnvoi.LIVRE):  # jamais en arrière
        changer_statut_envoi(db, envoi, statut, quand=email.date)
    vente = db.get(Vente, envoi.vente_id)
    email.vente_id = envoi.vente_id
    email.article_id = vente.article_id if vente else None
    email.statut_traitement = StatutTraitementEmail.TRAITE


def _annulation(db: Session, email: EmailVinted, article: Article | None) -> None:
    """Commande annulée sur Vinted : la vente est retirée, l'article redevient en ligne."""
    d = email.donnees_extraites or {}
    envoi = _envoi_de_article(db, article) if article else trouver_envoi(db, d, date_mail=email.date)
    vente = db.get(Vente, envoi.vente_id) if envoi else None
    if vente is not None:
        email.article_id = vente.article_id
        annuler_vente(db, vente, commentaire="Commande annulée sur Vinted")
    # La vente annulée n'est plus à confirmer.
    titres = titres_du_mail(d.get("titre_article"))
    ventes_en_attente = db.scalars(
        select(EmailVinted)
        .where(
            EmailVinted.type_detecte == TypeEmail.VENTE,
            EmailVinted.statut_traitement == StatutTraitementEmail.NOUVEAU,
            EmailVinted.date <= (email.date or utcnow()),
        )
        .order_by(EmailVinted.date.desc())
    ).all()
    for mail in ventes_en_attente:
        if titre_cle((mail.donnees_extraites or {}).get("titre_article")) in titres:
            mail.statut_traitement = StatutTraitementEmail.TRAITE
            break
    email.statut_traitement = StatutTraitementEmail.TRAITE


TYPES_SUIVI = [
    TypeEmail.BORDEREAU,
    TypeEmail.EXPEDIE,
    TypeEmail.LIVRE,
    TypeEmail.LITIGE,
    TypeEmail.ANNULATION,
]


def rejouer_mails_de_la_vente(db: Session, vente: Vente) -> int:
    """Après une vente confirmée : traite, dans l'ordre, les mails déjà reçus pour ce titre
    (bordereau, expédition, livraison, annulation…) restés sans vente."""
    titre = titre_vente(db, vente)
    if not titre:
        return 0
    en_attente = db.scalars(
        select(EmailVinted)
        .where(
            EmailVinted.statut_traitement == StatutTraitementEmail.NOUVEAU,
            EmailVinted.type_detecte.in_([t.value for t in TYPES_SUIVI]),
            EmailVinted.vente_id.is_(None),
            EmailVinted.date >= vente.date_heure,
        )
        .order_by(EmailVinted.date)
    ).all()
    rejoues = 0
    for mail in en_attente:
        if titre in titres_du_mail((mail.donnees_extraites or {}).get("titre_article")):
            appliquer(db, mail)
            rejoues += 1
    return rejoues


def retraiter_mails(db: Session) -> int:
    """Reclasse et retraite, dans l'ordre chronologique, tous les mails sans vente ni rattachement
    manuel (après une mise à jour des règles). Renvoie le nombre de mails dont le type a changé."""
    regles = regles_actives(db)
    changes = 0
    # Mails déjà rattachés à une vente : on garde leur traitement, on complète seulement les données
    # extraites (le titre Vinted sert à relier les mails suivants).
    for lie in db.scalars(select(EmailVinted).where(EmailVinted.vente_id.is_not(None))):
        relu = classifieur.classer(regles, mail_depuis_email(db, lie))
        if relu.type == lie.type_detecte:
            lie.donnees_extraites = (lie.donnees_extraites or {}) | relu.donnees
    db.flush()
    ids = db.scalars(
        select(EmailVinted.id)
        .where(
            EmailVinted.vente_id.is_(None),
            EmailVinted.statut_traitement != StatutTraitementEmail.IGNORE,
            or_(
                EmailVinted.statut_traitement != StatutTraitementEmail.TRAITE,
                EmailVinted.article_id.is_(None),
                EmailVinted.type_detecte.in_([TypeEmail.MESSAGE.value, TypeEmail.OFFRE.value]),
            ),
        )
        .order_by(EmailVinted.date, EmailVinted.id)
    ).all()
    for email_id in ids:
        email = db.get(EmailVinted, email_id)
        if email is None or email.vente_id is not None:
            continue  # déjà traité en cascade par une vente rapprochée plus tôt dans la boucle
        resultat = classifieur.classer(regles, mail_depuis_email(db, email))
        changes += resultat.type != email.type_detecte
        email.type_detecte = resultat.type
        email.regle_id = resultat.regle_id
        email.donnees_extraites = resultat.donnees
        if resultat.type is None:
            email.statut_traitement = StatutTraitementEmail.A_CLASSER
        else:
            email.statut_traitement = StatutTraitementEmail.NOUVEAU
            appliquer(db, email)
        db.flush()
    annuler_en_attente(db)  # relecture : aucune notification
    db.commit()
    return changes


def etapes_par_titre(db: Session) -> dict[str, list[tuple[datetime, str]]]:
    """Étapes de commande connues par titre (bordereau, en route, reçue, annulée, litige), datées."""
    etapes: dict[str, list[tuple[datetime, str]]] = {}
    for mail in db.scalars(
        select(EmailVinted).where(EmailVinted.type_detecte.in_([t.value for t in TYPES_SUIVI]))
    ):
        for t in titres_du_mail((mail.donnees_extraites or {}).get("titre_article")):
            etapes.setdefault(t, []).append((mail.date or utcnow(), str(mail.type_detecte)))
    return etapes


def etape_commande(
    etapes: dict[str, list[tuple[datetime, str]]], titre: str | None, depuis: datetime | None
) -> str | None:
    """Dernière étape connue d'une commande depuis la vente (aide à confirmer une vente ancienne)."""
    suivantes = [
        (quand, type_)
        for t in titres_du_mail(titre)
        for quand, type_ in etapes.get(t, [])
        if depuis is None or quand >= depuis
    ]
    return max(suivantes)[1] if suivantes else None


# Mails qui rendent caduc un mail de suivi antérieur au même titre (le colis est parti, arrivé, annulé…)
CLOTURE = {
    TypeEmail.BORDEREAU: {TypeEmail.EXPEDIE, TypeEmail.LIVRE, TypeEmail.ANNULATION, TypeEmail.LITIGE},
    TypeEmail.EXPEDIE: {TypeEmail.LIVRE, TypeEmail.ANNULATION},
}


def mails_termines(db: Session) -> set[int]:
    """Mails de suivi restés sans vente mais dont il n'y a plus rien à faire : un mail ultérieur au
    même titre montre que l'étape est passée (bordereau puis colis en route, colis en route puis reçu…),
    la vente a été ignorée, ou c'est un mail de réception (la commande est terminée)."""
    suites: list[tuple[str, set[str], datetime]] = []
    for mail in db.scalars(
        select(EmailVinted).where(
            EmailVinted.type_detecte.in_(
                [
                    t.value
                    for t in (TypeEmail.EXPEDIE, TypeEmail.LIVRE, TypeEmail.ANNULATION, TypeEmail.LITIGE)
                ]
            )
            | (
                (EmailVinted.type_detecte == TypeEmail.VENTE)
                & (EmailVinted.statut_traitement == StatutTraitementEmail.IGNORE)
            )
        )
    ):
        titres = set(titres_du_mail((mail.donnees_extraites or {}).get("titre_article")))
        suites.append((str(mail.type_detecte), titres, mail.date or utcnow()))
    termines = set()
    for mail in db.scalars(
        select(EmailVinted).where(
            EmailVinted.statut_traitement == StatutTraitementEmail.NOUVEAU,
            EmailVinted.type_detecte.in_(
                [TypeEmail.BORDEREAU.value, TypeEmail.EXPEDIE.value, TypeEmail.LIVRE.value]
            ),
        )
    ):
        if mail.type_detecte == TypeEmail.LIVRE:
            termines.add(mail.id)
            continue
        fermants = {t.value for t in CLOTURE[TypeEmail(str(mail.type_detecte))]} | {TypeEmail.VENTE.value}
        titres = set(titres_du_mail((mail.donnees_extraites or {}).get("titre_article")))
        quand = mail.date or utcnow()
        if any(type_ in fermants and t & titres and date > quand for type_, t, date in suites):
            termines.add(mail.id)
    return termines


# --- Litiges et messages ----------------------------------------------------------------------


def _article_par_titre(
    db: Session,
    titre: str | None,
    statuts: list[StatutArticle],
    doublons_ok: bool = False,
    compte_id: int | None = None,
) -> Article | None:
    """Article dont le nom correspond nettement au titre. `doublons_ok` : si les meilleurs candidats sont
    des exemplaires identiques (même nom, même prix), le premier convient (utile pour un message)."""
    if not titre:
        return None
    articles = db.scalars(
        rapprochement.du_compte(
            select(Article).where(Article.statut.in_([s.value for s in statuts])), compte_id
        ).order_by(Article.id)
    ).all()
    scores = sorted(
        ((rapprochement.score_titre(titre, a), a) for a in articles), key=lambda x: x[0], reverse=True
    )
    if not scores or scores[0][0] < SEUIL_TITRE:
        return None
    meilleur = scores[0][1]
    if len(scores) == 1 or scores[0][0] - scores[1][0] >= 10:
        return meilleur
    if doublons_ok:
        ex_aequo = [a for sc, a in scores if scores[0][0] - sc < 10]
        identiques = all(
            normaliser(a.nom) == normaliser(meilleur.nom) and a.prix_vente_cible == meilleur.prix_vente_cible
            for a in ex_aequo
        )
        if identiques:
            return meilleur
    return None


def _litige(db: Session, email: EmailVinted, article: Article | None) -> None:
    d = email.donnees_extraites or {}
    if article is None:
        envoi = trouver_envoi(db, d, statuts_ouverts=False, date_mail=email.date)
        vente = db.get(Vente, envoi.vente_id) if envoi else None
        article = db.get(Article, vente.article_id) if vente else None
    if article is None:
        article = _article_par_titre(
            db,
            d.get("titre_article"),
            [StatutArticle.VENDU, StatutArticle.ENVOYE, StatutArticle.LIVRE],
            compte_id=email.compte_id,
        )
    # Même non rattaché, un litige est signalé tout de suite.
    notifier(
        db,
        "litige",
        "Nouveau litige",
        f"/stock/{article.id}" if article else "/mails",
        corps=article.nom if article else "",
        compte_id=(article.compte_id if article else None) or email.compte_id,
    )
    if article is None:
        email.statut_traitement = StatutTraitementEmail.NOUVEAU
        return
    changer_statut(
        db, article, StatutArticle.LITIGE, quand=email.date, commentaire="Litige signalé par Vinted"
    )
    email.article_id = article.id
    email.statut_traitement = StatutTraitementEmail.TRAITE


def _message(db: Session, email: EmailVinted, article: Article | None) -> None:
    d = email.donnees_extraites or {}
    # Un message porte presque toujours sur un article en ligne : on cherche d'abord là.
    for statuts in ([StatutArticle.EN_LIGNE], [StatutArticle.RECU_A_PUBLIER, StatutArticle.VENDU]):
        if article is not None:
            break
        article = _article_par_titre(
            db, d.get("titre_article"), statuts, doublons_ok=True, compte_id=email.compte_id
        )
    existant = db.scalar(select(Message).where(Message.email_id == email.id))
    if existant is None:
        db.add(
            Message(
                email_id=email.id,
                type=email.type_detecte,
                acheteur=d.get("acheteur"),
                article_id=article.id if article else None,
                extrait=(email.corps_texte or "")[:1000],
                montant_offre=_decimal(d.get("montant_offre")),
                statut=StatutMessage.A_TRAITER,
            )
        )
    elif article is not None:
        existant.article_id = article.id
    nom = article.nom if article else d.get("titre_article") or ""
    if email.type_detecte == TypeEmail.OFFRE:
        montant = _decimal(d.get("montant_offre"))
        titre = (
            "💰 Offre" + (f" de {_prix_texte(montant)}" if montant else "") + (f" sur {nom}" if nom else "")
        )
        affiche = _decimal(d.get("prix_affiche"))
        corps = _detail_offre(db, article, montant, affiche, d.get("acheteur"))
        notifier(db, "offre", titre, "/messages", corps=corps)
    else:
        titre = "💬 Message" + (f" de {d['acheteur']}" if d.get("acheteur") else "")
        notifier(db, "message", titre, "/messages", corps=nom)
    email.article_id = article.id if article else None
    email.statut_traitement = StatutTraitementEmail.TRAITE


DECISIONS = {"accepter": "accepter", "contre_proposer": "contre-proposer", "refuser": "refuser"}


def _detail_offre(
    db: Session,
    article: Article | None,
    montant: Decimal | None,
    affiche: Decimal | None,
    acheteur: str | None,
) -> str:
    """« Affiché 40 € (−13 %) · conseil : contre-proposer 38 € · sophie.b ». Le prix affiché vient
    du mail (« au lieu de »), sinon de la fiche article."""
    morceaux = []
    params = db.get(Parametres, 1)
    if affiche is None and article is not None:
        affiche = stats.prix_vente(article)
    if montant is not None and affiche:
        ecart = round((montant - affiche) / affiche * 100)
        morceaux.append(f"Affiché {_prix_texte(affiche)} ({ecart:+d} %)".replace("-", "−"))
    if article is not None and montant is not None and params is not None:
        analyse = offres.analyser(article, montant, params)
        conseil = f"conseil : {DECISIONS[analyse.decision]}"
        if analyse.montant_propose is not None:
            conseil += f" {_prix_texte(analyse.montant_propose)}"
        morceaux.append(conseil)
    if acheteur:
        morceaux.append(acheteur)
    return " · ".join(morceaux)


def _favori(db: Session, email: EmailVinted, article: Article | None) -> None:
    d = email.donnees_extraites or {}
    if article is None:
        article = _article_par_titre(
            db, d.get("titre_article"), [StatutArticle.EN_LIGNE], doublons_ok=True, compte_id=email.compte_id
        )
    if article is not None:
        affiche = stats.prix_vente(article)
        corps = article.nom + (f" · {_prix_texte(affiche)}" if affiche else "")
        notifier(db, "favori", "❤️ Nouveau favori", f"/stock/{article.id}", corps=corps)
    else:
        notifier(
            db, "favori", "❤️ Nouveau favori", "/mails", corps=d.get("titre_article") or email.sujet or ""
        )
    email.article_id = article.id if article else None
    email.statut_traitement = StatutTraitementEmail.TRAITE


# --- Classement manuel ------------------------------------------------------------------------


def mail_depuis_email(db: Session, email: EmailVinted) -> MailLu:
    """Reconstruit le mail lu à partir de ce qui est stocké (pour reclasser ou tester une règle)."""
    pieces = db.scalars(select(PieceJointe).where(PieceJointe.email_id == email.id)).all()
    return MailLu(
        message_id=email.message_id,
        date=email.date,
        expediteur=email.expediteur or "",
        sujet=email.sujet or "",
        texte=email.corps_texte or "",
        html=email.corps_html or "",
        pieces_jointes=[PieceJointeBrute(nom=p.nom, mime=p.mime, contenu=b"") for p in pieces],
        liens=liens_html(email.corps_html) if email.corps_html else re_liens(email.corps_texte or ""),
    )


def reclasser(db: Session, email: EmailVinted, type_email: TypeEmail) -> None:
    """Classement manuel : on applique l'extraction de la première règle du type choisi."""
    regles = sorted((r for r in regles_actives(db) if r.type_cible == type_email), key=lambda r: r.priorite)
    email.type_detecte = type_email
    email.regle_id = regles[0].id if regles else None
    email.donnees_extraites = classifieur.extraire(regles[0], mail_depuis_email(db, email)) if regles else {}
    email.statut_traitement = StatutTraitementEmail.NOUVEAU
    appliquer(db, email)
