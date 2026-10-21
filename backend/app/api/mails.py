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
from app.models import Article, CompteVinted, EmailVinted, PieceJointe, RegleClassement, SyncLog
from app.models.enums import StatutTraitementEmail, TypeEmail
from app.seed import regles as seed
from app.services import classifieur, crypto, imap_sync, storage, traitement
from app.services.marques import normaliser

router = APIRouter(tags=["mails"])


# --- Configuration IMAP -----------------------------------------------------------------------


class CompteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nom: str
    imap_serveur: str
    imap_port: int
    imap_email: str
    imap_dossier: str
    actif: bool
    derniere_synchro: datetime | None
    nb_articles: int = 0
    nb_mails: int = 0


class ConfigMailsOut(BaseModel):
    comptes: list[CompteOut]
    expediteurs: list[str]
    presets: dict[str, dict[str, Any]]


class CompteIn(BaseModel):
    nom: str = Field(min_length=1, max_length=80)
    serveur: str = Field(min_length=3, max_length=255)
    port: int = Field(default=993, ge=1, le=65535)
    email: str = Field(min_length=3, max_length=255)
    # Vide = conserver le mot de passe déjà enregistré
    mot_de_passe: str | None = None
    dossier: str = Field(default="INBOX", min_length=1, max_length=255)
    actif: bool = True


class TestImapIn(BaseModel):
    serveur: str = Field(min_length=3, max_length=255)
    port: int = Field(default=993, ge=1, le=65535)
    email: str = Field(min_length=3, max_length=255)
    mot_de_passe: str | None = None
    dossier: str = Field(default="INBOX", min_length=1, max_length=255)
    # Compte existant : son mot de passe enregistré sert si aucun n'est saisi
    compte_id: int | None = None


class ExpediteursIn(BaseModel):
    expediteurs: list[str]


def _compte_out(db: Db, c: CompteVinted) -> CompteOut:
    out = CompteOut.model_validate(c)
    out.nb_articles = db.scalar(select(func.count(Article.id)).where(Article.compte_id == c.id)) or 0
    out.nb_mails = db.scalar(select(func.count(EmailVinted.id)).where(EmailVinted.compte_id == c.id)) or 0
    return out


def _config_out(db: Db) -> ConfigMailsOut:
    comptes = db.scalars(select(CompteVinted).order_by(CompteVinted.id)).all()
    return ConfigMailsOut(
        comptes=[_compte_out(db, c) for c in comptes],
        expediteurs=get_parametres(db).expediteurs_vinted or [],
        presets=imap_sync.PRESETS,
    )


def _get_compte(db: Db, compte_id: int) -> CompteVinted:
    compte = db.get(CompteVinted, compte_id)
    if compte is None:
        raise HTTPException(404, "Compte introuvable.")
    return compte


def _chiffrer(mot_de_passe: str) -> str:
    try:
        return crypto.chiffrer(mot_de_passe)
    except crypto.CleManquante as exc:
        raise HTTPException(500, str(exc)) from exc


def _verifier_unicite(db: Db, email: str, sauf: int | None = None) -> None:
    requete = select(CompteVinted.id).where(func.lower(CompteVinted.imap_email) == email.lower())
    if sauf is not None:
        requete = requete.where(CompteVinted.id != sauf)
    if db.scalar(requete):
        raise HTTPException(409, f"La boîte {email} est déjà branchée sur un autre compte.")


@router.get("/parametres/mails", response_model=ConfigMailsOut)
def lire_config_mails(db: Db) -> ConfigMailsOut:
    return _config_out(db)


@router.put("/parametres/mails/expediteurs", response_model=ConfigMailsOut)
def enregistrer_expediteurs(data: ExpediteursIn, db: Db) -> ConfigMailsOut:
    get_parametres(db).expediteurs_vinted = [e.strip() for e in data.expediteurs if e.strip()] or ["vinted"]
    db.commit()
    return _config_out(db)


@router.get("/comptes", response_model=list[CompteOut])
def lister_comptes(db: Db) -> list[CompteOut]:
    return _config_out(db).comptes


@router.post("/comptes", response_model=CompteOut, status_code=201)
def creer_compte(data: CompteIn, db: Db) -> CompteOut:
    if not data.mot_de_passe:
        raise HTTPException(422, "Saisis le mot de passe (d'application) de la boîte mail.")
    _verifier_unicite(db, data.email.strip())
    compte = CompteVinted(
        nom=data.nom.strip(),
        imap_serveur=data.serveur.strip(),
        imap_port=data.port,
        imap_email=data.email.strip(),
        imap_mot_de_passe_chiffre=_chiffrer(data.mot_de_passe),
        imap_dossier=data.dossier.strip(),
        actif=data.actif,
    )
    db.add(compte)
    db.commit()
    return _compte_out(db, compte)


@router.put("/comptes/{compte_id}", response_model=CompteOut)
def modifier_compte(compte_id: int, data: CompteIn, db: Db) -> CompteOut:
    compte = _get_compte(db, compte_id)
    _verifier_unicite(db, data.email.strip(), sauf=compte.id)
    if data.mot_de_passe:
        compte.imap_mot_de_passe_chiffre = _chiffrer(data.mot_de_passe)
    if data.email.strip().lower() != compte.imap_email.lower() or data.dossier.strip() != compte.imap_dossier:
        compte.derniere_synchro = None  # nouvelle boîte : on relit les 30 derniers jours
    compte.nom = data.nom.strip()
    compte.imap_serveur = data.serveur.strip()
    compte.imap_port = data.port
    compte.imap_email = data.email.strip()
    compte.imap_dossier = data.dossier.strip()
    compte.actif = data.actif
    db.commit()
    return _compte_out(db, compte)


@router.post("/comptes/{compte_id}/relire", response_model=CompteOut)
def relire_historique(compte_id: int, db: Db) -> CompteOut:
    """La prochaine synchro relit toute la boîte depuis le début de l'activité (les mails déjà
    importés sont reconnus par leur Message-ID et ignorés)."""
    compte = _get_compte(db, compte_id)
    compte.derniere_synchro = None
    db.commit()
    return _compte_out(db, compte)


@router.delete("/comptes/{compte_id}", status_code=204)
def supprimer_compte(compte_id: int, db: Db) -> None:
    """Débranche la boîte. Les mails, ventes et articles déjà importés sont conservés."""
    db.delete(_get_compte(db, compte_id))
    db.commit()


@router.post("/imap/test")
def tester_imap(data: TestImapIn, db: Db) -> dict[str, Any]:
    mot_de_passe = data.mot_de_passe
    if not mot_de_passe:
        if data.compte_id is None:
            raise HTTPException(422, "Saisis le mot de passe (d'application) de la boîte mail.")
        try:
            mot_de_passe = crypto.dechiffrer(_get_compte(db, data.compte_id).imap_mot_de_passe_chiffre)
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
    compte_id: int | None


@router.post("/imap/sync", response_model=list[SyncOut])
def synchroniser(db: Db) -> list[SyncLog]:
    try:
        return imap_sync.synchroniser(db, get_parametres(db))
    except imap_sync.ErreurImap as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/imap/logs", response_model=list[SyncOut])
def journal(db: Db) -> list[SyncLog]:
    return list(db.scalars(select(SyncLog).order_by(SyncLog.debut.desc()).limit(20)))


# --- Mails ------------------------------------------------------------------------------------


def _email_resume(
    e: EmailVinted, regles: dict[int, str], articles: dict[int, str], comptes: dict[int, str]
) -> dict[str, Any]:
    return {
        "id": e.id,
        "compte_id": e.compte_id,
        "compte": comptes.get(e.compte_id) if e.compte_id else None,
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
    compte: int | None = None,
    page: int = Query(1, ge=1),
    taille_page: int = Query(50, ge=1, le=200),
) -> dict[str, Any]:
    q = select(EmailVinted)
    if statut:
        q = q.where(EmailVinted.statut_traitement.in_([s.value for s in statut]))
    if type:
        q = q.where(EmailVinted.type_detecte.in_([t.value for t in type]))
    if compte is not None:
        q = q.where(EmailVinted.compte_id == compte)
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
        "items": [_email_resume(e, regles, articles, imap_sync.noms_comptes(db)) for e in emails],
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
    articles = {article.id: article.nom} if article else {}
    return _email_resume(e, regles, articles, imap_sync.noms_comptes(db)) | {
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
