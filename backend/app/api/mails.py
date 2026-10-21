"""Configuration IMAP, synchronisation, mails et règles de classement."""

import re
from collections import Counter
from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.deps import Db, get_parametres
from app.models import Article, EmailVinted, PieceJointe, RegleClassement, SyncLog
from app.models.enums import StatutTraitementEmail, TypeEmail
from app.seed import regles as seed
from app.services import classifieur, crypto, imap_sync, storage, traitement
from app.services.marques import normaliser

router = APIRouter(tags=["mails"])


# --- Configuration IMAP -----------------------------------------------------------------------


class ImapOut(BaseModel):
    serveur: str | None
    port: int | None
    email: str | None
    dossier: str
    mot_de_passe_defini: bool
    expediteurs: list[str]
    derniere_synchro: datetime | None
    presets: dict[str, dict[str, Any]]


class ImapIn(BaseModel):
    serveur: str = Field(min_length=3, max_length=255)
    port: int = Field(default=993, ge=1, le=65535)
    email: str = Field(min_length=3, max_length=255)
    # Vide = conserver le mot de passe déjà enregistré
    mot_de_passe: str | None = None
    dossier: str = Field(default="INBOX", min_length=1, max_length=255)
    expediteurs: list[str] = Field(default_factory=lambda: ["vinted"])


def _imap_out(db: Db) -> ImapOut:
    p = get_parametres(db)
    return ImapOut(
        serveur=p.imap_serveur,
        port=p.imap_port,
        email=p.imap_email,
        dossier=p.imap_dossier,
        mot_de_passe_defini=bool(p.imap_mot_de_passe_chiffre),
        expediteurs=p.expediteurs_vinted or [],
        derniere_synchro=p.derniere_synchro,
        presets=imap_sync.PRESETS,
    )


@router.get("/parametres/imap", response_model=ImapOut)
def lire_imap(db: Db) -> ImapOut:
    return _imap_out(db)


@router.put("/parametres/imap", response_model=ImapOut)
def enregistrer_imap(data: ImapIn, db: Db) -> ImapOut:
    p = get_parametres(db)
    if data.mot_de_passe:
        try:
            p.imap_mot_de_passe_chiffre = crypto.chiffrer(data.mot_de_passe)
        except crypto.CleManquante as exc:
            raise HTTPException(500, str(exc)) from exc
    elif not p.imap_mot_de_passe_chiffre:
        raise HTTPException(422, "Saisis le mot de passe (d'application) de la boîte mail.")
    p.imap_serveur = data.serveur.strip()
    p.imap_port = data.port
    p.imap_email = data.email.strip()
    p.imap_dossier = data.dossier.strip()
    p.expediteurs_vinted = [e.strip() for e in data.expediteurs if e.strip()] or ["vinted"]
    db.commit()
    return _imap_out(db)


@router.post("/imap/test")
def tester_imap(data: ImapIn, db: Db) -> dict[str, Any]:
    p = get_parametres(db)
    mot_de_passe = data.mot_de_passe
    if not mot_de_passe:
        if not p.imap_mot_de_passe_chiffre:
            raise HTTPException(422, "Saisis le mot de passe (d'application) de la boîte mail.")
        try:
            mot_de_passe = crypto.dechiffrer(p.imap_mot_de_passe_chiffre)
        except crypto.CleManquante as exc:
            raise HTTPException(500, str(exc)) from exc
    cfg = imap_sync.ConfigImap(
        data.serveur.strip(), data.port, data.email.strip(), mot_de_passe, data.dossier
    )
    try:
        nb = imap_sync.tester_connexion(cfg)
    except imap_sync.ErreurImap as exc:
        return {"ok": False, "message": str(exc)}
    return {"ok": True, "message": f"Connexion réussie : {nb} mail(s) dans « {data.dossier} »."}


class SyncOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    debut: datetime
    fin: datetime | None
    nb_mails: int
    erreur: str | None


@router.post("/imap/sync", response_model=SyncOut)
def synchroniser(db: Db) -> SyncLog:
    try:
        return imap_sync.synchroniser(db, get_parametres(db))
    except imap_sync.ErreurImap as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/imap/logs", response_model=list[SyncOut])
def journal(db: Db) -> list[SyncLog]:
    return list(db.scalars(select(SyncLog).order_by(SyncLog.debut.desc()).limit(20)))


# --- Mails ------------------------------------------------------------------------------------


def _email_resume(e: EmailVinted, regles: dict[int, str], articles: dict[int, str]) -> dict[str, Any]:
    return {
        "id": e.id,
        "date": e.date,
        "expediteur": e.expediteur,
        "sujet": e.sujet,
        "type_detecte": e.type_detecte,
        "statut_traitement": e.statut_traitement,
        "regle_nom": regles.get(e.regle_id) if e.regle_id else None,
        "donnees_extraites": e.donnees_extraites or {},
        "article_id": e.article_id,
        "article_nom": articles.get(e.article_id) if e.article_id else None,
        "vente_id": e.vente_id,
        "extrait": " ".join((e.corps_texte or "").split())[:240],
    }


@router.get("/emails")
def lister_emails(
    db: Db,
    statut: list[StatutTraitementEmail] | None = Query(None),
    type: list[TypeEmail] | None = Query(None),
    page: int = Query(1, ge=1),
    taille_page: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    q = select(EmailVinted)
    if statut:
        q = q.where(EmailVinted.statut_traitement.in_([s.value for s in statut]))
    if type:
        q = q.where(EmailVinted.type_detecte.in_([t.value for t in type]))
    total = db.scalar(select(func.count()).select_from(q.subquery())) or 0
    emails = db.scalars(
        q.order_by(EmailVinted.date.desc()).offset((page - 1) * taille_page).limit(taille_page)
    ).all()
    regles = dict(db.execute(select(RegleClassement.id, RegleClassement.nom)).tuples().all())
    ids_articles = {e.article_id for e in emails if e.article_id}
    articles = (
        dict(db.execute(select(Article.id, Article.nom).where(Article.id.in_(ids_articles))).tuples().all())
        if ids_articles
        else {}
    )
    return {
        "items": [_email_resume(e, regles, articles) for e in emails],
        "total": total,
        "compteurs": dict(
            db.execute(
                select(EmailVinted.statut_traitement, func.count()).group_by(EmailVinted.statut_traitement)
            )
            .tuples()
            .all()
        ),
    }


def _get_email(db: Db, email_id: int) -> EmailVinted:
    email = db.get(EmailVinted, email_id)
    if email is None:
        raise HTTPException(404, "Mail introuvable.")
    return email


@router.get("/emails/{email_id}")
def detail_email(email_id: int, db: Db) -> dict[str, Any]:
    e = _get_email(db, email_id)
    pieces = db.scalars(select(PieceJointe).where(PieceJointe.email_id == e.id)).all()
    regles = dict(db.execute(select(RegleClassement.id, RegleClassement.nom)).tuples().all())
    article = db.get(Article, e.article_id) if e.article_id else None
    return _email_resume(e, regles, {article.id: article.nom} if article else {}) | {
        "corps_texte": e.corps_texte,
        "corps_html": e.corps_html,
        "pieces_jointes": [{"id": p.id, "nom": p.nom, "mime": p.mime} for p in pieces],
    }


class ClasserIn(BaseModel):
    type: TypeEmail | None = None  # None = ignorer le mail


@router.post("/emails/{email_id}/classer")
def classer_email(email_id: int, data: ClasserIn, db: Db) -> dict[str, Any]:
    email = _get_email(db, email_id)
    if data.type is None:
        email.statut_traitement = StatutTraitementEmail.IGNORE
    else:
        traitement.reclasser(db, email, data.type)
    db.commit()
    return detail_email(email_id, db)


class RattacherIn(BaseModel):
    article_id: int


@router.post("/emails/{email_id}/rattacher")
def rattacher_email(email_id: int, data: RattacherIn, db: Db) -> dict[str, Any]:
    """Applique l'action du mail (bordereau, livraison, litige, message…) à l'article choisi."""
    email = _get_email(db, email_id)
    article = db.get(Article, data.article_id)
    if article is None:
        raise HTTPException(404, "Article introuvable.")
    if not email.type_detecte:
        raise HTTPException(422, "Classe d'abord ce mail.")
    if email.type_detecte == TypeEmail.VENTE:
        raise HTTPException(422, "Pour une vente, utilise « Ventes à confirmer ».")
    traitement.appliquer(db, email, article)
    if email.statut_traitement != StatutTraitementEmail.TRAITE:
        db.rollback()
        raise HTTPException(
            422,
            "Impossible de rattacher ce mail à cet article (pas d'envoi en cours, ou bordereau absent du mail).",
        )
    db.commit()
    return detail_email(email_id, db)


@router.get("/pieces-jointes/{piece_id}")
def piece_jointe(piece_id: int, db: Db) -> FileResponse:
    p = db.get(PieceJointe, piece_id)
    if p is None:
        raise HTTPException(404, "Pièce jointe introuvable.")
    chemin = storage.chemin_absolu(p.chemin)
    if not chemin.exists():
        raise HTTPException(404, "Le fichier n'existe plus sur le serveur.")
    return FileResponse(chemin, media_type=p.mime, filename=p.nom, content_disposition_type="inline")


# --- Assistant « créer une règle à partir de ce mail » ----------------------------------------

MOTS_VIDES = set(
    [
        "pour",
        "avec",
        "dans",
        "votre",
        "vous",
        "tu",
        "ton",
        "ta",
        "tes",
        "sur",
        "les",
        "des",
        "une",
        "est",
        "sont",
        "que",
        "qui",
        "pas",
        "plus",
        "a",
        "au",
        "aux",
        "du",
        "de",
        "la",
        "le",
        "et",
        "ou",
        "en",
        "un",
        "ce",
        "cet",
        "cette",
        "son",
        "sa",
        "ses",
        "nous",
        "ils",
        "elles",
        "mais",
        "par",
        "vinted",
        "bonjour",
        "salut",
    ]
)


def _mots_cles_sujet(sujet: str, n: int = 3) -> list[str]:
    mots = [
        m for m in re.findall(r"[\wàâçéèêëîïôûùüÿœ'-]{4,}", sujet.lower()) if normaliser(m) not in MOTS_VIDES
    ]
    mots = [m for m in mots if not re.search(r"\d", m)]
    return [m for m, _ in Counter(mots).most_common(n)]


@router.post("/emails/{email_id}/suggestion-regle")
def suggestion_regle(email_id: int, db: Db) -> dict[str, Any]:
    email = _get_email(db, email_id)
    mail = traitement.mail_depuis_email(db, email)
    domaine = (email.expediteur or "").split("@")[-1]
    conditions: dict[str, Any] = {"expediteurs": [domaine] if domaine else ["vinted"]}
    mots = _mots_cles_sujet(email.sujet or "")
    if mots:
        # Le mot le plus long du sujet est en général le plus distinctif.
        conditions["sujet_contient"] = [max(mots, key=len)]
    # On propose chaque motif d'extraction connu qui trouve quelque chose dans ce mail.
    candidats = {
        "prix": seed.PRIX,
        "titre_article": seed.TITRE,
        "numero_commande": seed.COMMANDE,
        "acheteur": seed.ACHETEUR,
        "date_limite": seed.DATE_LIMITE,
        "lien_bordereau": seed.LIEN_BORDEREAU,
    }
    essai = RegleClassement(
        id=0, nom="suggestion", type_cible="autre", conditions=conditions, extraction=candidats
    )
    trouves = classifieur.extraire(essai, mail)
    extraction = {k: v for k, v in candidats.items() if k in trouves}
    return {
        "nom": f"Règle : {email.sujet[:60]}" if email.sujet else "Nouvelle règle",
        "type_cible": email.type_detecte,
        "priorite": 85,
        "conditions": conditions,
        "extraction": extraction,
        "apercu": trouves,
    }


# --- Règles -----------------------------------------------------------------------------------


class RegleIn(BaseModel):
    nom: str = Field(min_length=1, max_length=120)
    type_cible: TypeEmail
    conditions: dict[str, Any] = Field(default_factory=dict)
    extraction: dict[str, str] = Field(default_factory=dict)
    priorite: int = Field(default=100, ge=0, le=10_000)
    active: bool = True


class RegleOut(RegleIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


def _valider_regle(data: RegleIn) -> None:
    for cle in ("sujet_regex", "corps_regex"):
        if data.conditions.get(cle):
            _compiler(data.conditions[cle], cle)
    for champ, motif in data.extraction.items():
        if champ not in classifieur.CHAMPS_EXTRACTION:
            raise HTTPException(422, f"Champ d'extraction inconnu : {champ}.")
        if motif:
            _compiler(motif, champ)
    listes = ("expediteurs", "sujet_contient", "corps_contient")
    if not any(data.conditions.get(k) for k in (*listes, "sujet_regex", "corps_regex", "piece_jointe_pdf")):
        raise HTTPException(422, "Ajoute au moins une condition à la règle.")


def _compiler(motif: str, champ: str) -> None:
    try:
        re.compile(motif)
    except re.error as exc:
        raise HTTPException(422, f"Expression régulière invalide pour « {champ} » : {exc}.") from exc


@router.get("/regles", response_model=list[RegleOut])
def lister_regles(db: Db) -> list[RegleClassement]:
    return list(db.scalars(select(RegleClassement).order_by(RegleClassement.priorite, RegleClassement.id)))


@router.post("/regles", response_model=RegleOut, status_code=201)
def creer_regle(data: RegleIn, db: Db) -> RegleClassement:
    _valider_regle(data)
    regle = RegleClassement(**data.model_dump())
    db.add(regle)
    db.commit()
    db.refresh(regle)
    return regle


@router.put("/regles/{regle_id}", response_model=RegleOut)
def modifier_regle(regle_id: int, data: RegleIn, db: Db) -> RegleClassement:
    regle = db.get(RegleClassement, regle_id)
    if regle is None:
        raise HTTPException(404, "Règle introuvable.")
    _valider_regle(data)
    for cle, valeur in data.model_dump().items():
        setattr(regle, cle, valeur)
    db.commit()
    db.refresh(regle)
    return regle


@router.delete("/regles/{regle_id}", status_code=204)
def supprimer_regle(regle_id: int, db: Db) -> None:
    regle = db.get(RegleClassement, regle_id)
    if regle is None:
        raise HTTPException(404, "Règle introuvable.")
    db.delete(regle)
    db.commit()


class TestRegleIn(RegleIn):
    email_ids: list[int] | None = None


@router.post("/regles/tester")
def tester_regle(data: TestRegleIn, db: Db) -> dict[str, Any]:
    """Essaie une règle (non enregistrée) sur des mails donnés ou sur les 200 derniers."""
    _valider_regle(data)
    q = select(EmailVinted)
    q = (
        q.where(EmailVinted.id.in_(data.email_ids))
        if data.email_ids
        else q.order_by(EmailVinted.date.desc()).limit(200)
    )
    regle = RegleClassement(id=0, **data.model_dump(exclude={"email_ids"}))
    resultats = []
    for email in db.scalars(q):
        mail = traitement.mail_depuis_email(db, email)
        if classifieur.correspond(regle, mail):
            resultats.append(
                {
                    "id": email.id,
                    "sujet": email.sujet,
                    "date": email.date,
                    "extraction": classifieur.extraire(regle, mail),
                }
            )
    return {"nb_correspondances": len(resultats), "exemples": resultats[:20]}


@router.post("/regles/reappliquer")
def reappliquer(db: Db) -> dict[str, int]:
    """Reclasse les mails non classés avec les règles actuelles."""
    regles = traitement.regles_actives(db)
    reclasses = 0
    for email in db.scalars(
        select(EmailVinted).where(EmailVinted.statut_traitement == StatutTraitementEmail.A_CLASSER)
    ).all():
        resultat = classifieur.classer(regles, traitement.mail_depuis_email(db, email))
        if resultat.type:
            email.type_detecte = resultat.type
            email.regle_id = resultat.regle_id
            email.donnees_extraites = resultat.donnees
            email.statut_traitement = StatutTraitementEmail.NOUVEAU
            traitement.appliquer(db, email)
            reclasses += 1
    db.commit()
    return {"reclasses": reclasses}
