"""Routes appelées par l'extension Chrome (en-tête X-Extension-Token), hors session de l'app.

L'extension n'a que le minimum : elle exécute ce que le backend lui donne et remonte ce qu'elle voit.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field

from app.api.deps import Db, get_parametres
from app.models import Article, CompteVinted, PhotoArticle
from app.services import alertes, brouillons, extension

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


def _compte_out(db: Db, compte: CompteVinted) -> CompteOut:
    return CompteOut(
        compte_id=compte.id,
        nom=compte.nom,
        vinted_user_id=compte.vinted_user_id,
        pause=compte.pause,
        pause_raison=compte.pause_raison,
        brouillons_du_jour=brouillons.brouillons_du_jour(db, compte),
        brouillons_max_jour=brouillons.max_par_jour(compte),
    )


@router.get("/compte", response_model=CompteOut)
def lire_compte(compte: Compte, db: Db) -> CompteOut:
    return _compte_out(db, compte)


class HeartbeatIn(BaseModel):
    vinted_user_id: int | None = None
    login: str | None = Field(default=None, max_length=120)
    version: str | None = Field(default=None, max_length=40)


@router.post("/heartbeat", response_model=CompteOut)
def heartbeat(data: HeartbeatIn, compte: Compte, db: Db) -> CompteOut:
    extension.battement(db, compte, data.vinted_user_id, data.login, data.version)
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
    charge = brouillons.prochain(db, compte, get_parametres(db))
    return charge if charge is not None else Response(status_code=204)


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
    article = _article_du_compte(db, compte, article_id)
    if article.brouillon_statut != "en_cours":
        raise HTTPException(409, "Ce brouillon n'est pas en cours.")
    if data.ok and data.vinted_draft_id is None:
        raise HTTPException(422, "vinted_draft_id manquant.")
    brouillons.enregistrer_resultat(
        db, compte, article, data.ok, data.vinted_draft_id, data.erreur, data.ai_photo
    )
    if data.arret:
        alertes.arreter_compte(db, compte, data.erreur or "Réponse inattendue de Vinted.")
    alertes.valider(db)
