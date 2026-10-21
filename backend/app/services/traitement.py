"""Traitement d'un mail Vinted : enregistrement, classement, puis action selon son type.

Statut de traitement d'un mail :
- `traite` : l'action a été faite (vente créée, bordereau rattaché, statut mis à jour…)
- `nouveau` : type reconnu mais action en attente (vente à confirmer, bordereau ou livraison à rattacher)
- `a_classer` : aucune règle ne correspond
- `ignore` : écarté à la main
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from rapidfuzz import fuzz
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Article, EmailVinted, Envoi, Message, PieceJointe, RegleClassement, Vente
from app.models.enums import (
    StatutArticle,
    StatutEnvoi,
    StatutMessage,
    StatutTraitementEmail,
    TypeEmail,
)
from app.services import classifieur, rapprochement, storage
from app.services.email_parser import MailLu, PieceJointeBrute, liens_html, re_liens
from app.services.marques import normaliser
from app.services.notifications import notifier
from app.services.statuts import changer_statut

DELAI_ENVOI_JOURS_OUVRES = 5  # délai Vinted pour expédier après une vente
SEUIL_TITRE = 75.0

# Statut d'article associé à chaque statut d'envoi.
ARTICLE_PAR_ENVOI = {StatutEnvoi.DEPOSE: StatutArticle.ENVOYE, StatutEnvoi.LIVRE: StatutArticle.LIVRE}


def regles_actives(db: Session) -> list[RegleClassement]:
    return list(db.scalars(select(RegleClassement).where(RegleClassement.active.is_(True))))


def _date(v: Any) -> datetime | None:
    return datetime.fromisoformat(v) if isinstance(v, str) else None


# --- Enregistrement ---------------------------------------------------------------------------


def enregistrer_mail(db: Session, mail: MailLu) -> EmailVinted | None:
    """Enregistre, classe et traite un mail. Renvoie None s'il est déjà connu (Message-ID)."""
    if db.scalar(select(EmailVinted.id).where(EmailVinted.message_id == mail.message_id)):
        return None
    resultat = classifieur.classer(regles_actives(db), mail)
    email = EmailVinted(
        message_id=mail.message_id,
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
    db.commit()
    return email


def appliquer(db: Session, email: EmailVinted, article: Article | None = None) -> None:
    """Exécute l'action du type détecté. `article` force l'article concerné (rattachement manuel)."""
    actions = {
        TypeEmail.VENTE: _vente,
        TypeEmail.BORDEREAU: _bordereau,
        TypeEmail.EXPEDIE: _suivi_colis,
        TypeEmail.LIVRE: _suivi_colis,
        TypeEmail.LITIGE: _litige,
        TypeEmail.MESSAGE: _message,
        TypeEmail.OFFRE: _message,
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
        liste = rapprochement.candidats(db, d.get("titre_article"), _decimal(d.get("prix")))
        choix = rapprochement.choix_automatique(liste)
        if choix is None:
            email.statut_traitement = StatutTraitementEmail.NOUVEAU  # -> « Ventes à confirmer »
            notifier("vente", "Nouvelle vente à confirmer", "/ventes")
            return
        article = db.get(Article, choix.article_id)
        assert article is not None
        confirmer_vente(db, email, article, auto=True)
    else:
        confirmer_vente(db, email, article, auto=False)


def _decimal(v: Any) -> Decimal | None:
    return Decimal(v) if isinstance(v, str) and v else None


def confirmer_vente(db: Session, email: EmailVinted, article: Article, auto: bool) -> Vente:
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
    notifier("vente", f"Vendu : {article.nom}", f"/stock/{article.id}")
    return vente


def annuler_vente(db: Session, vente: Vente) -> None:
    """Annule un rapprochement : l'article repasse en ligne et le mail revient « à confirmer »."""
    article = db.get(Article, vente.article_id)
    if article is not None:
        changer_statut(db, article, StatutArticle.EN_LIGNE, commentaire="Rapprochement annulé")
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


def trouver_envoi(db: Session, donnees: dict[str, Any], statuts_ouverts: bool = True) -> Envoi | None:
    """Envoi concerné par un mail : par numéro de commande, sinon par titre d'article."""
    requete = select(Envoi, Vente, Article).join(Vente, Envoi.vente_id == Vente.id).join(Article)
    if statuts_ouverts:
        requete = requete.where(Envoi.statut != StatutEnvoi.LIVRE)
    lignes = db.execute(requete).all()
    if numero := donnees.get("numero_commande"):
        for envoi, vente, _ in lignes:
            if vente.numero_commande and vente.numero_commande == numero:
                return envoi
    if titre := donnees.get("titre_article"):
        scores = sorted(
            ((fuzz.token_set_ratio(normaliser(titre), normaliser(a.nom)), e) for e, _, a in lignes),
            key=lambda x: x[0],
            reverse=True,
        )
        if scores and scores[0][0] >= SEUIL_TITRE and (len(scores) == 1 or scores[0][0] - scores[1][0] >= 10):
            return scores[0][1]
    return None


def _envoi_de_article(db: Session, article: Article) -> Envoi | None:
    return db.scalar(
        select(Envoi).join(Vente).where(Vente.article_id == article.id).order_by(Vente.date_heure.desc())
    )


def _bordereau(db: Session, email: EmailVinted, article: Article | None) -> None:
    d = email.donnees_extraites or {}
    envoi = _envoi_de_article(db, article) if article else trouver_envoi(db, d)
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
    envoi = _envoi_de_article(db, article) if article else trouver_envoi(db, d)
    if envoi is None:
        email.statut_traitement = StatutTraitementEmail.NOUVEAU
        return
    statut = StatutEnvoi.LIVRE if email.type_detecte == TypeEmail.LIVRE else StatutEnvoi.DEPOSE
    changer_statut_envoi(db, envoi, statut, quand=email.date)
    vente = db.get(Vente, envoi.vente_id)
    email.vente_id = envoi.vente_id
    email.article_id = vente.article_id if vente else None
    email.statut_traitement = StatutTraitementEmail.TRAITE


# --- Litiges et messages ----------------------------------------------------------------------


def _article_par_titre(
    db: Session, titre: str | None, statuts: list[StatutArticle], doublons_ok: bool = False
) -> Article | None:
    """Article dont le nom correspond nettement au titre. `doublons_ok` : si les meilleurs candidats sont
    des exemplaires identiques (même nom, même prix), le premier convient (utile pour un message)."""
    if not titre:
        return None
    articles = db.scalars(
        select(Article).where(Article.statut.in_([s.value for s in statuts])).order_by(Article.id)
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
        envoi = trouver_envoi(db, d, statuts_ouverts=False)
        vente = db.get(Vente, envoi.vente_id) if envoi else None
        article = db.get(Article, vente.article_id) if vente else None
    if article is None:
        article = _article_par_titre(
            db, d.get("titre_article"), [StatutArticle.VENDU, StatutArticle.ENVOYE, StatutArticle.LIVRE]
        )
    # Même non rattaché, un litige est signalé tout de suite.
    notifier("litige", "Nouveau litige", f"/stock/{article.id}" if article else "/mails")
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
        article = _article_par_titre(db, d.get("titre_article"), statuts, doublons_ok=True)
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
    if email.type_detecte == TypeEmail.OFFRE:
        notifier("offre", "Nouvelle offre", "/messages")
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
