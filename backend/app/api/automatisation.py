"""Pilotage de l'automatisation Vinted depuis l'app : comptes, jetons d'extension, pause, journal."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.deps import Db, get_parametres
from app.models import Article, CompteVinted, JournalVinted, PhotoArticle, TacheVinted
from app.services import alertes, brouillons, couleur, extension, file_vinted, reglages, taches, telegram

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
    telegram_relie: bool
    telegram_code: str | None
    telegram_code_expire_le: datetime | None
    budget_utilise: dict[str, int]
    budget_plafonds: dict[str, int]
    file: dict[str, int]


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
        telegram_relie=c.telegram_chat_id is not None,
        telegram_code=c.telegram_code,
        telegram_code_expire_le=c.telegram_code_expire_le,
        budget_utilise=taches.utilisation(db, c),
        budget_plafonds=taches.plafonds(c),
        file=file_vinted.en_file(db, c),
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
    """Reprise manuelle, seule façon de sortir d'un arrêt automatique."""
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


# --- Interrupteur global, réglages, Telegram -------------------------------------------------


class GlobalOut(BaseModel):
    automatisation_active: bool
    telegram_configure: bool
    modules: list[str]
    types_alertes: dict[str, str]


def _global(db: Db) -> GlobalOut:
    return GlobalOut(
        automatisation_active=get_parametres(db).automatisation_active,
        telegram_configure=telegram.configure(),
        modules=list(reglages.MODULES),
        types_alertes=reglages.TYPES_ALERTES,
    )


@router.get("/automatisation/global", response_model=GlobalOut)
def lire_global(db: Db) -> GlobalOut:
    return _global(db)


class GlobalIn(BaseModel):
    automatisation_active: bool


@router.put("/automatisation/global", response_model=GlobalOut)
def modifier_global(data: GlobalIn, db: Db) -> GlobalOut:
    """Arrêt d'urgence de tous les comptes (rien n'est perdu : les tâches restent en file)."""
    get_parametres(db).automatisation_active = data.automatisation_active
    alertes.journaliser(
        db,
        None,
        "global",
        "Automatisation réactivée." if data.automatisation_active else "Arrêt d'urgence global.",
    )
    db.commit()
    return _global(db)


@router.get("/automatisation/comptes/{compte_id}/reglages")
def lire_reglages(compte_id: int, db: Db) -> dict[str, Any]:
    return reglages.du_compte(_compte(db, compte_id))


@router.put("/automatisation/comptes/{compte_id}/reglages")
def modifier_reglages(compte_id: int, data: dict[str, Any], db: Db) -> dict[str, Any]:
    """Modifications partielles (par section) ; les valeurs absentes gardent leur réglage."""
    c = _compte(db, compte_id)
    try:
        nouveaux = reglages.enregistrer(c, data)
    except (reglages.ReglageInvalide, KeyError, TypeError) as exc:
        raise HTTPException(422, f"Réglage invalide : {exc}") from exc
    alertes.journaliser(db, c, "reglages", "Réglages modifiés : " + ", ".join(sorted(data)) + ".")
    db.commit()
    return nouveaux


@router.post("/automatisation/comptes/{compte_id}/telegram", response_model=CompteAutoOut)
def code_telegram(compte_id: int, db: Db) -> CompteAutoOut:
    """Code à 6 chiffres à envoyer au bot avec /start (valable 30 min)."""
    c = _compte(db, compte_id)
    telegram.generer_code(c)
    db.commit()
    return _out(db, c)


@router.delete("/automatisation/comptes/{compte_id}/telegram", response_model=CompteAutoOut)
def delier_telegram(compte_id: int, db: Db) -> CompteAutoOut:
    c = _compte(db, compte_id)
    c.telegram_chat_id = None
    alertes.journaliser(db, c, "telegram", "Telegram délié.")
    db.commit()
    return _out(db, c)


# --- File de tâches --------------------------------------------------------------------------


class TacheOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    compte_id: int
    type: str
    article_id: int | None
    payload: dict[str, Any]
    priorite: int
    executer_apres: datetime
    statut: str
    resultat: dict[str, Any] | None
    erreur: str | None
    created_at: datetime
    debut_le: datetime | None
    fin_le: datetime | None


@router.get("/automatisation/taches", response_model=list[TacheOut])
def lister_taches(
    db: Db,
    compte_id: int | None = None,
    statut: list[str] | None = Query(default=None),
    limite: int = Query(default=100, ge=1, le=500),
) -> list[TacheVinted]:
    q = select(TacheVinted).order_by(TacheVinted.created_at.desc(), TacheVinted.id.desc()).limit(limite)
    if compte_id is not None:
        q = q.where(TacheVinted.compte_id == compte_id)
    if statut:
        q = q.where(TacheVinted.statut.in_(statut))
    return list(db.scalars(q))


def _tache(db: Db, tache_id: int) -> tuple[TacheVinted, CompteVinted]:
    t = db.get(TacheVinted, tache_id)
    if t is None:
        raise HTTPException(404, "Tâche introuvable.")
    c = db.get(CompteVinted, t.compte_id)
    assert c is not None
    return t, c


class ValiderTacheIn(BaseModel):
    texte: str | None = Field(default=None, min_length=1, max_length=2000)


@router.post("/automatisation/taches/{tache_id}/valider", response_model=TacheOut)
def valider_tache(tache_id: int, data: ValiderTacheIn, db: Db) -> TacheVinted:
    """Action proposée par l'assistant, validée (et éventuellement corrigée) depuis l'app."""
    t, c = _tache(db, tache_id)
    if t.statut != "a_valider":
        raise HTTPException(409, "Cette tâche n'attend pas de validation.")
    if data.texte:
        t.payload = {**t.payload, "texte": data.texte}
    file_vinted.valider_tache(db, c, t)
    alertes.journaliser(db, c, "validation", f"Tâche {t.id} validée depuis l'app.")
    db.commit()
    return t


@router.post("/automatisation/taches/{tache_id}/annuler", response_model=TacheOut)
def annuler_tache(tache_id: int, db: Db) -> TacheVinted:
    t, c = _tache(db, tache_id)
    if t.statut not in ("a_faire", "a_valider"):
        raise HTTPException(409, "Seule une tâche en attente peut être annulée.")
    t.statut = "annulee"
    alertes.journaliser(db, c, "annulation", f"Tâche {t.id} ({t.type}) annulée depuis l'app.")
    db.commit()
    return t


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


@router.post("/articles/{article_id}/republication/debloquer", status_code=204)
def debloquer_republication(article_id: int, db: Db) -> None:
    """Après un échec, Lucas a vérifié l'annonce sur Vinted : la republication automatique peut reprendre."""
    a = db.get(Article, article_id)
    if a is None:
        raise HTTPException(404, "Article introuvable.")
    a.republication_bloquee = False
    compte = db.get(CompteVinted, a.compte_id) if a.compte_id else None
    alertes.journaliser(db, compte, "republication", f"Republication réautorisée : {a.nom}.", article_id=a.id)
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
