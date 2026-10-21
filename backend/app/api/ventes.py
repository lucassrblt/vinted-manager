"""Ventes à confirmer, ventes, envois et bordereaux."""

from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from sqlalchemy import select

from app.api import creation
from app.api.deps import Db
from app.db import utcnow
from app.models import Article, EmailVinted, Envoi, Vente
from app.models.enums import StatutArticle, StatutEnvoi, StatutTraitementEmail, TypeEmail
from app.services import bordereaux, rapprochement, storage, traitement
from app.services.imap_sync import noms_comptes
from app.services.statuts import changer_statut

router = APIRouter(tags=["ventes"])


# --- Ventes -----------------------------------------------------------------------------------


@router.get("/ventes/a-confirmer")
def ventes_a_confirmer(db: Db) -> list[dict[str, Any]]:
    emails = db.scalars(
        select(EmailVinted)
        .where(
            EmailVinted.type_detecte == TypeEmail.VENTE,
            EmailVinted.statut_traitement == StatutTraitementEmail.NOUVEAU,
        )
        .order_by(EmailVinted.date.desc())
    ).all()
    resultat = []
    comptes = noms_comptes(db)
    etapes = traitement.etapes_par_titre(db)
    for e in emails:
        d = e.donnees_extraites or {}
        prix = Decimal(d["prix"]) if d.get("prix") else None
        candidats = rapprochement.candidats(
            db, d.get("titre_article"), prix, compte_id=e.compte_id, date_mail=e.date
        )
        resultat.append(
            {
                "email_id": e.id,
                "date": e.date,
                "sujet": e.sujet,
                "compte": comptes.get(e.compte_id) if e.compte_id else None,
                "etape": traitement.etape_commande(etapes, d.get("titre_article"), e.date),
                "donnees": d,
                "candidats": [c.__dict__ for c in candidats],
            }
        )
    return resultat


class PiecePersoIn(BaseModel):
    email_id: int


@router.post("/ventes/piece-perso")
def vente_piece_perso(data: PiecePersoIn, db: Db) -> dict[str, Any]:
    """Vente d'une de tes propres pièces, absente du stock : l'article est créé depuis le mail
    (coût 0 €), puis la vente est confirmée et ses mails de suivi appliqués."""
    email = db.get(EmailVinted, data.email_id)
    if email is None or email.type_detecte != TypeEmail.VENTE:
        raise HTTPException(404, "Mail de vente introuvable.")
    if email.vente_id:
        raise HTTPException(409, "Cette vente est déjà confirmée.")
    d = email.donnees_extraites or {}
    titre = str(d.get("titre_article") or email.sujet or "Pièce perso")[:255]
    article = Article(nom=titre, titre_annonce=titre[:120], compte_id=email.compte_id)
    creation.marquer_perso(article)
    db.add(article)
    changer_statut(
        db,
        article,
        StatutArticle.EN_LIGNE,
        quand=email.date,
        commentaire="Pièce perso (depuis le mail de vente)",
    )
    db.flush()
    vente = traitement.confirmer_vente(db, email, article, auto=False)
    db.commit()
    return {"vente_id": vente.id, "article_id": article.id}


class ConfirmerIn(BaseModel):
    email_id: int
    article_id: int


@router.post("/ventes/confirmer")
def confirmer(data: ConfirmerIn, db: Db) -> dict[str, Any]:
    email = db.get(EmailVinted, data.email_id)
    article = db.get(Article, data.article_id)
    if email is None or article is None:
        raise HTTPException(404, "Mail ou article introuvable.")
    if email.type_detecte != TypeEmail.VENTE or email.vente_id:
        raise HTTPException(409, "Cette vente est déjà confirmée.")
    importe_sans_vente = article.statut in rapprochement.STATUTS_A_COMPLETER and not db.scalar(
        select(Vente.id).where(Vente.article_id == article.id)
    )
    if (
        article.statut not in (StatutArticle.EN_LIGNE, StatutArticle.RECU_A_PUBLIER)
        and not importe_sans_vente
    ):
        raise HTTPException(409, f"Cet article n'est pas en vente (statut : {article.statut}).")
    vente = traitement.confirmer_vente(db, email, article, auto=False)
    db.commit()
    return {"vente_id": vente.id, "article_id": article.id}


@router.post("/ventes/{vente_id}/annuler", status_code=204)
def annuler(vente_id: int, db: Db) -> None:
    vente = db.get(Vente, vente_id)
    if vente is None:
        raise HTTPException(404, "Vente introuvable.")
    envoi = db.scalar(select(Envoi).where(Envoi.vente_id == vente_id))
    if envoi and envoi.statut in (StatutEnvoi.DEPOSE, StatutEnvoi.LIVRE):
        raise HTTPException(409, "Le colis est déjà déposé : la vente ne peut plus être annulée ici.")
    traitement.annuler_vente(db, vente)
    db.commit()


@router.get("/ventes")
def lister_ventes(db: Db, jours: int = Query(30, ge=1, le=3650)) -> list[dict[str, Any]]:
    depuis = utcnow() - timedelta(days=jours)
    lignes = db.execute(
        select(Vente, Article)
        .join(Article, Vente.article_id == Article.id)
        .where(Vente.date_heure >= depuis)
        .order_by(Vente.date_heure.desc())
    ).all()
    return [
        {
            "id": v.id,
            "prix": v.prix,
            "date_heure": v.date_heure,
            "acheteur": v.acheteur,
            "numero_commande": v.numero_commande,
            "auto_rapproche": v.auto_rapproche,
            "article": {"id": a.id, "nom": a.nom, "taille": a.taille, "statut": a.statut},
        }
        for v, a in lignes
    ]


# --- Envois -----------------------------------------------------------------------------------


def _envoi_out(e: Envoi, v: Vente, a: Article) -> dict[str, Any]:
    return {
        "id": e.id,
        "statut": e.statut,
        "transporteur": e.transporteur,
        "date_limite_envoi": e.date_limite_envoi,
        "date_depot": e.date_depot,
        "a_bordereau_pdf": bool(e.fichier_bordereau),
        "lien_bordereau": e.lien_bordereau,
        "vente": {
            "id": v.id,
            "prix": v.prix,
            "acheteur": v.acheteur,
            "numero_commande": v.numero_commande,
            "date_heure": v.date_heure,
        },
        "article": {"id": a.id, "nom": a.nom, "taille": a.taille, "statut": a.statut},
    }


@router.get("/envois")
def lister_envois(db: Db, termines: bool = False) -> dict[str, Any]:
    q = (
        select(Envoi, Vente, Article)
        .join(Vente, Envoi.vente_id == Vente.id)
        .join(Article, Vente.article_id == Article.id)
    )
    q = q.where(Envoi.statut == StatutEnvoi.LIVRE) if termines else q.where(Envoi.statut != StatutEnvoi.LIVRE)
    lignes = db.execute(q.order_by(Envoi.date_limite_envoi.asc().nulls_last())).all()
    a_rattacher = db.scalars(
        select(EmailVinted)
        .where(
            EmailVinted.type_detecte == TypeEmail.BORDEREAU,
            EmailVinted.statut_traitement == StatutTraitementEmail.NOUVEAU,
        )
        .order_by(EmailVinted.date.desc())
    ).all()
    termines_sans_vente = traitement.mails_termines(db)  # déjà envoyés et reçus : plus rien à faire
    a_rattacher = [m for m in a_rattacher if m.id not in termines_sans_vente]
    return {
        "envois": [_envoi_out(e, v, a) for e, v, a in lignes],
        "bordereaux_a_rattacher": [
            {"email_id": m.id, "date": m.date, "sujet": m.sujet, "donnees": m.donnees_extraites or {}}
            for m in a_rattacher
        ],
    }


class EnvoiUpdate(BaseModel):
    statut: StatutEnvoi | None = None
    transporteur: str | None = None
    date_limite_envoi: datetime | None = None


@router.patch("/envois/{envoi_id}")
def modifier_envoi(envoi_id: int, data: EnvoiUpdate, db: Db) -> dict[str, Any]:
    envoi = db.get(Envoi, envoi_id)
    if envoi is None:
        raise HTTPException(404, "Envoi introuvable.")
    champs = data.model_dump(exclude_unset=True)
    if "transporteur" in champs:
        envoi.transporteur = champs["transporteur"]
    if champs.get("date_limite_envoi"):
        envoi.date_limite_envoi = champs["date_limite_envoi"]
    if data.statut and data.statut != envoi.statut:
        traitement.changer_statut_envoi(db, envoi, data.statut)
    db.commit()
    vente = db.get(Vente, envoi.vente_id)
    assert vente is not None
    article = db.get(Article, vente.article_id)
    assert article is not None
    return _envoi_out(envoi, vente, article)


@router.get("/envois/{envoi_id}/bordereau")
def bordereau(envoi_id: int, db: Db) -> FileResponse:
    envoi = db.get(Envoi, envoi_id)
    if envoi is None or not envoi.fichier_bordereau:
        raise HTTPException(404, "Pas de bordereau PDF pour cet envoi.")
    chemin = storage.chemin_absolu(envoi.fichier_bordereau)
    if not chemin.exists():
        raise HTTPException(404, "Le fichier du bordereau n'existe plus sur le serveur.")
    return FileResponse(chemin, media_type="application/pdf", filename=f"bordereau-{envoi_id}.pdf")


@router.get("/envois/bordereaux.pdf")
def bordereaux_fusionnes(
    db: Db,
    ids: list[int] = Query(...),
    format: Literal["a4", "10x15"] = "a4",
    marquer_imprimes: bool = False,
) -> Response:
    envois = db.scalars(select(Envoi).where(Envoi.id.in_(ids), Envoi.fichier_bordereau.is_not(None))).all()
    contenus = []
    # Même ordre que la page Envois : date limite la plus proche d'abord.
    for e in sorted(
        envois, key=lambda e: (e.date_limite_envoi is None, e.date_limite_envoi or utcnow(), e.id)
    ):
        assert e.fichier_bordereau is not None
        chemin = storage.chemin_absolu(e.fichier_bordereau)
        if chemin.exists():
            contenus.append(chemin.read_bytes())
    if not contenus:
        raise HTTPException(
            404, "Aucun bordereau PDF parmi les envois choisis (les liens s'ouvrent un par un)."
        )
    try:
        pdf = bordereaux.fusionner(contenus, format_10x15=format == "10x15")
    except Exception as exc:  # PDF corrompu
        raise HTTPException(422, "Un des bordereaux est illisible : télécharge-les un par un.") from exc
    if marquer_imprimes:
        for e in envois:
            if e.statut == StatutEnvoi.A_IMPRIMER:
                traitement.changer_statut_envoi(db, e, StatutEnvoi.IMPRIME)
        db.commit()
    nom = f"bordereaux-{utcnow():%Y%m%d-%H%M}{'-10x15' if format == '10x15' else ''}.pdf"
    return Response(
        pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{nom}"'}
    )
