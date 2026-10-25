"""Routes appelées par l'extension Chrome (en-tête X-Extension-Token), hors session de l'app.

L'extension n'a que le minimum : elle exécute ce que le backend lui donne et remonte ce qu'elle voit.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import Db, get_parametres
from app.models import Article, CompteVinted, PhotoArticle, TacheVinted
from app.services import alertes, brouillons, extension, file_vinted, horaires, reglages
from app.services import assistant as _assistant  # noqa: F401  (enregistre ses événements et résultats)
from app.services import dressing as _dressing  # noqa: F401  (enregistre l'événement « dressing »)
from app.services import favoris as _favoris  # noqa: F401  (événement « notifications », relances)

router = APIRouter(prefix="/extension", tags=["extension"])


def compte_extension(
    db: Db, x_extension_token: Annotated[str | None, Header(alias="X-Extension-Token")] = None
) -> CompteVinted:
    compte = extension.compte_du_jeton(db, x_extension_token)
    if compte is None:
        raise HTTPException(
            401, "Jeton d'extension invalide : génère-en un dans Paramètres → Automatisation."
        )
    return compte


Compte = Annotated[CompteVinted, Depends(compte_extension)]


class CompteOut(BaseModel):
    compte_id: int
    nom: str
    vinted_user_id: int | None
    pause: bool
    pause_raison: str | None
    brouillons_du_jour: int
    brouillons_max_jour: int
    # Réglages utiles à l'extension (relus à chaque cycle) : cadence de surveillance de Vinted.
    automatisation_active: bool
    heures_actives: bool
    heure_debut: int
    heure_fin: int
    modules: dict[str, bool]


def _compte_out(db: Db, compte: CompteVinted) -> CompteOut:
    r = reglages.du_compte(compte)
    return CompteOut(
        compte_id=compte.id,
        nom=compte.nom,
        vinted_user_id=compte.vinted_user_id,
        pause=compte.pause,
        pause_raison=compte.pause_raison,
        brouillons_du_jour=brouillons.brouillons_du_jour(db, compte),
        brouillons_max_jour=brouillons.max_par_jour(compte),
        automatisation_active=get_parametres(db).automatisation_active,
        heures_actives=horaires.actif(compte),
        heure_debut=int(r["heures"]["debut"]),
        heure_fin=int(r["heures"]["fin"]),
        modules=dict(r["modules"]),
    )


@router.get("/compte", response_model=CompteOut)
def lire_compte(compte: Compte, db: Db) -> CompteOut:
    return _compte_out(db, compte)


class HeartbeatIn(BaseModel):
    vinted_user_id: int | None = None
    login: str | None = Field(default=None, max_length=120)
    version: str | None = Field(default=None, max_length=40)
    # Un onglet www.vinted.fr est-il ouvert dans le profil ?
    onglet: bool | None = None


@router.post("/heartbeat", response_model=CompteOut)
def heartbeat(data: HeartbeatIn, compte: Compte, db: Db) -> CompteOut:
    extension.battement(db, compte, data.vinted_user_id, data.login, data.version, data.onglet)
    alertes.valider(db)
    return _compte_out(db, compte)


class ArretIn(BaseModel):
    raison: str = Field(min_length=1, max_length=500)


@router.post("/arret", response_model=CompteOut)
def arret(data: ArretIn, compte: Compte, db: Db) -> CompteOut:
    """Réponse Vinted inattendue observée par l'extension (401, 403, 429, captcha, non JSON)."""
    alertes.arreter_compte(db, compte, data.raison)
    alertes.valider(db)
    return _compte_out(db, compte)


@router.post("/pause", response_model=CompteOut)
def pause(compte: Compte, db: Db) -> CompteOut:
    """Bouton Pause de la popup."""
    compte.pause, compte.pause_raison = True, "Pause demandée depuis l'extension."
    alertes.journaliser(db, compte, "pause", "Pause demandée depuis l'extension.")
    db.commit()
    return _compte_out(db, compte)


@router.post("/reprendre", response_model=CompteOut)
def reprendre(compte: Compte, db: Db) -> CompteOut:
    """Bouton Reprendre de la popup : reprise manuelle (y compris après un arrêt automatique)."""
    compte.pause, compte.pause_raison = False, None
    alertes.journaliser(db, compte, "reprise", "Reprise demandée depuis l'extension.")
    db.commit()
    return _compte_out(db, compte)


@router.get("/brouillons/suivant")
def brouillon_suivant(compte: Compte, db: Db) -> object:
    """Route de la phase 1, conservée : le brouillon passe désormais par la file de tâches."""
    tache = file_vinted.suivante(db, compte, get_parametres(db), types={"brouillon"})
    return tache.payload if tache is not None else Response(status_code=204)


class TacheOut(BaseModel):
    id: int
    type: str
    article_id: int | None
    payload: dict[str, Any]
    executer_apres: datetime


@router.get("/taches/suivante", response_model=TacheOut)
def tache_suivante(compte: Compte, db: Db) -> object:
    tache = file_vinted.suivante(db, compte, get_parametres(db))
    if tache is None:
        return Response(status_code=204)
    return TacheOut(
        id=tache.id,
        type=tache.type,
        article_id=tache.article_id,
        payload=tache.payload,
        executer_apres=tache.executer_apres,
    )


class ResultatTacheIn(BaseModel):
    ok: bool
    resultat: dict[str, Any] | None = None
    erreur: str | None = Field(default=None, max_length=2000)
    # Réponse Vinted inattendue (401, 403, 429, captcha, non JSON) : le compte doit être arrêté.
    arret: bool = False
    # Échec renvoyé par Vinted (et non un contrôle préalable de l'extension).
    erreur_vinted: bool = False


def _terminer(db: Db, compte: CompteVinted, tache: TacheVinted, data: ResultatTacheIn) -> None:
    if tache.statut != "en_cours":
        raise HTTPException(409, "Cette tâche n'est pas en cours.")
    file_vinted.terminer(
        db, compte, tache, data.ok, data.resultat, data.erreur, data.arret, data.erreur_vinted
    )
    alertes.valider(db)


@router.post("/taches/{tache_id}/resultat", status_code=204)
def resultat_tache(tache_id: int, data: ResultatTacheIn, compte: Compte, db: Db) -> None:
    tache = db.get(TacheVinted, tache_id)
    if tache is None or tache.compte_id != compte.id:
        raise HTTPException(404, "Tâche introuvable pour ce compte.")
    if data.ok and tache.type == "brouillon" and not (data.resultat or {}).get("vinted_draft_id"):
        raise HTTPException(422, "vinted_draft_id manquant.")
    _terminer(db, compte, tache, data)


class EvenementIn(BaseModel):
    type: str = Field(min_length=1, max_length=40)
    donnees: dict[str, Any] = Field(default_factory=dict)


@router.post("/evenements")
def evenement(data: EvenementIn, compte: Compte, db: Db) -> dict[str, Any]:
    """Ce que l'extension observe sur Vinted. Le backend décide (règles, IA) et crée les tâches."""
    traitement = file_vinted.EVENEMENTS.get(data.type)
    if traitement is None:
        raise HTTPException(422, f"Événement inconnu : {data.type}.")
    reponse = traitement(db, compte, data.donnees)
    alertes.valider(db)
    return reponse


def _article_du_compte(db: Db, compte: CompteVinted, article_id: int) -> Article:
    article = db.get(Article, article_id)
    if article is None or article.compte_id != compte.id:
        raise HTTPException(404, "Article introuvable pour ce compte.")
    return article


@router.get("/photos/{photo_id}")
def photo(photo_id: int, compte: Compte, db: Db) -> Response:
    """JPEG tel qu'il sera publié, seulement pour un article de ce compte."""
    p = db.get(PhotoArticle, photo_id)
    if p is None:
        raise HTTPException(404, "Photo introuvable.")
    _article_du_compte(db, compte, p.article_id)
    try:
        contenu = brouillons.contenu_publie(p, get_parametres(db))
    except FileNotFoundError as exc:
        raise HTTPException(404, "Fichier introuvable sur le serveur.") from exc
    return Response(contenu, media_type="image/jpeg", headers={"Cache-Control": "no-store"})


class ResultatBrouillonIn(BaseModel):
    ok: bool
    vinted_draft_id: int | None = None
    ai_photo: bool | None = None
    erreur: str | None = Field(default=None, max_length=2000)
    # Réponse Vinted inattendue (401, 403, 429, captcha, non JSON) : le compte doit être arrêté.
    arret: bool = False


@router.post("/brouillons/{article_id}/resultat", status_code=204)
def resultat_brouillon(article_id: int, data: ResultatBrouillonIn, compte: Compte, db: Db) -> None:
    """Route de la phase 1, conservée : termine la tâche « brouillon » en cours de cet article."""
    _article_du_compte(db, compte, article_id)
    tache = db.scalar(
        select(TacheVinted).where(
            TacheVinted.compte_id == compte.id,
            TacheVinted.article_id == article_id,
            TacheVinted.type == "brouillon",
            TacheVinted.statut == "en_cours",
        )
    )
    if tache is None:
        raise HTTPException(409, "Ce brouillon n'est pas en cours.")
    if data.ok and data.vinted_draft_id is None:
        raise HTTPException(422, "vinted_draft_id manquant.")
    resultat = {"vinted_draft_id": data.vinted_draft_id, "ai_photo": data.ai_photo} if data.ok else None
    _terminer(
        db,
        compte,
        tache,
        ResultatTacheIn(ok=data.ok, resultat=resultat, erreur=data.erreur, arret=data.arret),
    )
