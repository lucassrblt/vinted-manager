"""Pilotage de l'automatisation Vinted depuis l'app : comptes, jetons d'extension, pause, journal."""

from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.deps import Db
from app.models import Article, CompteVinted, JournalVinted, PhotoArticle
from app.services import alertes, brouillons, couleur, extension

router = APIRouter(tags=["automatisation"])


class CompteAutoOut(BaseModel):
    id: int
    nom: str
    imap_configure: bool
    vinted_user_id: int | None
    vinted_user_id_vu: int | None
    vinted_login_vu: str | None
    jeton_defini: bool
    extension_vue_le: datetime | None
    extension_version: str | None
    pause: bool
    pause_raison: str | None
    brouillons_du_jour: int
    brouillons_max_jour: int


def _out(db: Db, c: CompteVinted) -> CompteAutoOut:
    return CompteAutoOut(
        id=c.id,
        nom=c.nom,
        imap_configure=c.imap_configure,
        vinted_user_id=c.vinted_user_id,
        vinted_user_id_vu=c.vinted_user_id_vu,
        vinted_login_vu=c.vinted_login_vu,
        jeton_defini=c.jeton_extension_hash is not None,
        extension_vue_le=c.extension_vue_le,
        extension_version=c.extension_version,
        pause=c.pause,
        pause_raison=c.pause_raison,
        brouillons_du_jour=brouillons.brouillons_du_jour(db, c),
        brouillons_max_jour=brouillons.max_par_jour(c),
    )


def _compte(db: Db, compte_id: int) -> CompteVinted:
    c = db.get(CompteVinted, compte_id)
    if c is None:
        raise HTTPException(404, "Compte introuvable.")
    return c


@router.get("/automatisation/comptes", response_model=list[CompteAutoOut])
def lister(db: Db) -> list[CompteAutoOut]:
    return [_out(db, c) for c in db.scalars(select(CompteVinted).order_by(CompteVinted.id))]


class NouveauCompteIn(BaseModel):
    nom: str = Field(min_length=1, max_length=80)


@router.post("/automatisation/comptes", response_model=CompteAutoOut, status_code=201)
def creer(data: NouveauCompteIn, db: Db) -> CompteAutoOut:
    """Compte piloté par l'extension, sans boîte mail (elle peut être ajoutée ensuite)."""
    c = CompteVinted(nom=data.nom.strip())
    db.add(c)
    db.commit()
    return _out(db, c)


class ModifCompteIn(BaseModel):
    vinted_user_id: int | None = Field(default=None, gt=0)
    # Reprend l'identifiant vu par l'extension comme identifiant attendu.
    confirmer_compte_vu: bool = False


@router.patch("/automatisation/comptes/{compte_id}", response_model=CompteAutoOut)
def modifier(compte_id: int, data: ModifCompteIn, db: Db) -> CompteAutoOut:
    c = _compte(db, compte_id)
    nouveau = c.vinted_user_id_vu if data.confirmer_compte_vu else data.vinted_user_id
    if data.confirmer_compte_vu and nouveau is None:
        raise HTTPException(409, "L'extension n'a encore vu aucun compte Vinted dans ce profil.")
    if "vinted_user_id" in data.model_fields_set or data.confirmer_compte_vu:
        if nouveau is not None:
            autre = db.scalar(
                select(CompteVinted.nom).where(
                    CompteVinted.vinted_user_id == nouveau, CompteVinted.id != c.id
                )
            )
            if autre:
                raise HTTPException(409, f"Cet identifiant Vinted est déjà celui du compte « {autre} ».")
        c.vinted_user_id = nouveau
    db.commit()
    return _out(db, c)


@router.post("/automatisation/comptes/{compte_id}/jeton")
def generer_jeton(compte_id: int, db: Db) -> dict[str, str]:
    """Le jeton n'est affiché qu'une fois : seul son empreinte est gardée."""
    c = _compte(db, compte_id)
    jeton = extension.generer_jeton(c)
    alertes.journaliser(db, c, "jeton", "Nouveau jeton d'extension généré (l'ancien ne fonctionne plus).")
    db.commit()
    return {"jeton": jeton}


@router.post("/automatisation/comptes/{compte_id}/pause", response_model=CompteAutoOut)
def mettre_en_pause(compte_id: int, db: Db) -> CompteAutoOut:
    c = _compte(db, compte_id)
    c.pause, c.pause_raison = True, "Pause manuelle."
    alertes.journaliser(db, c, "pause", "Pause manuelle.")
    db.commit()
    return _out(db, c)


@router.post("/automatisation/comptes/{compte_id}/reprendre", response_model=CompteAutoOut)
def reprendre(compte_id: int, db: Db) -> CompteAutoOut:
    c = _compte(db, compte_id)
    c.pause, c.pause_raison = False, None
    alertes.journaliser(db, c, "reprise", "Reprise manuelle.")
    db.commit()
    return _out(db, c)


class JournalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    compte_id: int | None
    date: datetime
    niveau: str
    type: str
    message: str
    article_id: int | None


@router.get("/automatisation/journal", response_model=list[JournalOut])
def journal(
    db: Db, compte_id: int | None = None, limite: int = Query(default=100, ge=1, le=500)
) -> list[JournalVinted]:
    q = select(JournalVinted).order_by(JournalVinted.date.desc(), JournalVinted.id.desc()).limit(limite)
    if compte_id is not None:
        q = q.where(JournalVinted.compte_id == compte_id)
    return list(db.scalars(q))


# --- Brouillons et contrôle de couleur, côté article -----------------------------------------


@router.post("/articles/{article_id}/brouillon/relancer", status_code=204)
def relancer_brouillon(article_id: int, db: Db) -> None:
    """Remet un brouillon en erreur dans la file (jamais fait automatiquement)."""
    a = db.get(Article, article_id)
    if a is None:
        raise HTTPException(404, "Article introuvable.")
    if a.brouillon_statut != "erreur":
        raise HTTPException(409, "Seul un brouillon en erreur peut être relancé.")
    a.brouillon_statut, a.brouillon_erreur = None, None
    db.commit()


@router.post("/photos/{photo_id}/valider-couleur", status_code=204)
def valider_couleur(photo_id: int, db: Db) -> None:
    """Lucas a comparé la photo retouchée avec l'original : la couleur est fidèle."""
    p = db.get(PhotoArticle, photo_id)
    if p is None:
        raise HTTPException(404, "Photo introuvable.")
    p.couleur_validee = True
    a = db.get(Article, p.article_id)
    restantes = db.scalar(
        select(func.count(PhotoArticle.id)).where(
            PhotoArticle.article_id == p.article_id,
            PhotoArticle.id != p.id,
            PhotoArticle.couleur_validee.is_(False),
            PhotoArticle.ecart_couleur > couleur.SEUIL_DELTA_E,
        )
    )
    if a is not None and not restantes:
        a.couleur_a_verifier = False
    db.commit()
