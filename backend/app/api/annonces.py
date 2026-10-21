"""Annonces (IA), prix conseillé, messages et offres, modèles d'annonce et de réponse."""

from dataclasses import asdict
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api import creation
from app.api.deps import Db, get_parametres
from app.config import get_settings
from app.db import utcnow
from app.models import Article, Message, ModeleAnnonce, ModeleReponse, Parametres
from app.models.enums import STATUTS_VENDUS, EtatArticle, StatutArticle, StatutMessage
from app.schemas.stock import ArticleOut, vers_out
from app.services import ia, offres, prix_conseille, stats
from app.services.marques import normaliser
from app.services.statuts import changer_statut

router = APIRouter(tags=["annonces"])


def _article(db: Db, article_id: int) -> Article:
    a = db.get(Article, article_id)
    if a is None:
        raise HTTPException(404, "Article introuvable.")
    return a


def _vendus(db: Db) -> list[Article]:
    return list(db.scalars(select(Article).where(Article.statut.in_([s.value for s in STATUTS_VENDUS]))))


def calculer_prix(db: Db, article: Article, params: Parametres | None = None) -> prix_conseille.PrixConseille:
    return prix_conseille.calculer(article, _vendus(db), params or get_parametres(db))


def _modele_pour(db: Db, categorie: str | None) -> ModeleAnnonce | None:
    if not categorie:
        return None
    for m in db.scalars(select(ModeleAnnonce)):
        if m.categorie and normaliser(m.categorie) == normaliser(categorie):
            return m
    return None


# --- Prix conseillé ---------------------------------------------------------------------------


@router.get("/articles/{article_id}/prix-conseille")
def prix(article_id: int, db: Db) -> dict[str, Any]:
    return asdict(calculer_prix(db, _article(db, article_id)))


# --- Annonces ---------------------------------------------------------------------------------


@router.get("/annonces/a-publier", response_model=list[ArticleOut])
def a_publier(db: Db) -> list[ArticleOut]:
    articles = db.scalars(
        select(Article)
        .where(Article.statut == StatutArticle.RECU_A_PUBLIER)
        .order_by(Article.created_at, Article.id)
    ).all()
    params = get_parametres(db)
    return [vers_out(a, params) for a in articles]


@router.get("/annonces/{article_id}")
def fiche_annonce(article_id: int, db: Db) -> dict[str, Any]:
    a = _article(db, article_id)
    modele = _modele_pour(db, a.categorie)
    return {
        "article": vers_out(a, get_parametres(db)),
        "prix_conseille": asdict(calculer_prix(db, a)),
        "retouche_possible": creation.retouche_possible(db),
        "modele_id": modele.id if modele else None,
        "ia_disponible": bool(get_settings().anthropic_api_key) or get_settings().ia_factice,
    }


class FicheIn(BaseModel):
    marque: str | None = None
    modele: str | None = None
    categorie: str | None = None
    taille: str | None = None
    couleur: str | None = None
    etat: EtatArticle | None = None
    matiere: str | None = None
    defauts: str | None = None
    mesures: dict[str, str] | None = None
    modele_annonce_id: int | None = None
    essai: int = Field(default=0, ge=0, le=20)
    # Régénérer seulement une partie, avec une consigne libre (« plus court », « plus vendeur »…)
    cible: Literal["tout", "titre", "description"] = "tout"
    consigne: str | None = Field(default=None, max_length=1500)


ETATS_LIBELLES = {
    "neuf_avec_etiquette": "Neuf avec étiquette",
    "neuf_sans_etiquette": "Neuf sans étiquette",
    "tres_bon_etat": "Très bon état",
    "bon_etat": "Bon état",
    "satisfaisant": "Satisfaisant",
}


@router.post("/annonces/{article_id}/generer")
def generer(article_id: int, data: FicheIn, db: Db) -> dict[str, Any]:
    a = _article(db, article_id)
    # La fiche complétée est enregistrée sur l'article (elle sert aussi aux réponses aux acheteurs).
    for cle, valeur in data.model_dump(exclude={"modele_annonce_id", "essai", "cible", "consigne"}).items():
        if cle == "mesures":
            valeur = {k: v for k, v in (valeur or {}).items() if v} or None
        setattr(a, cle, valeur or None)
    modele = (
        db.get(ModeleAnnonce, data.modele_annonce_id)
        if data.modele_annonce_id
        else _modele_pour(db, a.categorie)
    )
    fiche = _fiche(a)
    try:
        annonce = ia.generer_annonce(
            fiche,
            {
                "structure_titre": modele.structure_titre,
                "structure_description": modele.structure_description,
                "mots_cles": modele.mots_cles,
            }
            if modele
            else None,  # fmt: skip
            data.essai,
            data.consigne,
        )
    except ia.ErreurIA as exc:
        db.commit()  # la fiche saisie est conservée même si l'IA échoue
        raise HTTPException(502, str(exc)) from exc
    if data.cible in ("tout", "titre"):
        a.titre_annonce = annonce.titre
    if data.cible in ("tout", "description"):
        a.description_annonce = annonce.description
        a.mots_cles_annonce = ", ".join(annonce.mots_cles)
    db.commit()
    return {
        "titre": a.titre_annonce or annonce.titre,
        "description": a.description_annonce or annonce.description,
        "mots_cles": [m.strip() for m in (a.mots_cles_annonce or "").split(",") if m.strip()],
    }


def _fiche(a: Article) -> dict[str, Any]:
    return {
        "nom": a.nom,
        "marque": a.marque,
        "modele": a.modele,
        "categorie": a.categorie,
        "taille": a.taille,
        "couleur": a.couleur,
        "etat": ETATS_LIBELLES.get(a.etat or "", a.etat),
        "matiere": a.matiere,
        "defauts": a.defauts,
        "mesures": a.mesures,
    }


class PublierIn(BaseModel):
    prix: Decimal | None = Field(default=None, gt=0)
    titre: str | None = Field(default=None, max_length=120)
    description: str | None = None


@router.post("/annonces/{article_id}/publier", response_model=ArticleOut)
def publier(article_id: int, data: PublierIn, db: Db) -> ArticleOut:
    a = _article(db, article_id)
    if a.statut not in (StatutArticle.RECU_A_PUBLIER, StatutArticle.EN_LIGNE, StatutArticle.RETOURNE):
        raise HTTPException(409, "Seul un article reçu (ou retourné) peut être publié.")
    if data.prix is not None:
        a.prix_vente_cible = data.prix
    if data.titre is not None:
        a.titre_annonce = data.titre
    if data.description is not None:
        a.description_annonce = data.description
    maintenant = utcnow()
    if a.statut == StatutArticle.EN_LIGNE:
        a.date_publication = maintenant
    else:
        changer_statut(
            db, a, StatutArticle.EN_LIGNE, quand=maintenant, commentaire="Annonce publiée", forcer_date=True
        )
    db.commit()
    db.refresh(a)
    return vers_out(a, get_parametres(db))


# --- Messages et offres -----------------------------------------------------------------------


class MessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    type: str
    acheteur: str | None
    article_id: int | None
    extrait: str | None
    montant_offre: Decimal | None
    reponse_suggeree: str | None
    reponse_finale: str | None
    statut: str
    created_at: Any
    analyse: dict[str, Any] | None = None


def _analyse(a: Article | None, m: Message, params: Parametres) -> dict[str, Any] | None:
    if m.type != "offre" or a is None or m.montant_offre is None:
        return None
    return asdict(offres.analyser(a, m.montant_offre, params))


@router.get("/messages")
def lister_messages(db: Db, statut: list[StatutMessage] | None = Query(None)) -> list[dict[str, Any]]:
    """Messages et offres regroupés par article (les plus récents d'abord)."""
    q = select(Message).order_by(Message.created_at.desc())
    if statut:
        q = q.where(Message.statut.in_([s.value for s in statut]))
    messages = db.scalars(q).all()
    params = get_parametres(db)
    groupes: dict[int | None, dict[str, Any]] = {}
    for m in messages:
        a = db.get(Article, m.article_id) if m.article_id else None
        g = groupes.setdefault(
            m.article_id,
            {
                "article": {
                    "id": a.id,
                    "nom": a.nom,
                    "taille": a.taille,
                    "statut": a.statut,
                    "prix_vente": stats.prix_vente(a),
                    "prix_achat_net": a.prix_achat_net,
                }
                if a
                else None,  # fmt: skip
                "messages": [],
            },
        )
        out = MessageOut.model_validate(m)
        out.analyse = _analyse(a, m, params)
        g["messages"].append(out)
    return list(groupes.values())


@router.post("/messages/{message_id}/suggestion", response_model=MessageOut)
def suggestion(message_id: int, db: Db) -> MessageOut:
    m = db.get(Message, message_id)
    if m is None:
        raise HTTPException(404, "Message introuvable.")
    a = db.get(Article, m.article_id) if m.article_id else None
    params = get_parametres(db)
    analyse = _analyse(a, m, params)
    modeles = [{"contexte": r.contexte, "texte": r.texte} for r in db.scalars(select(ModeleReponse))]
    fiche = _fiche(a) | {"prix_affiche": str(stats.prix_vente(a))} if a else None
    try:
        m.reponse_suggeree = ia.suggerer_reponse(m.extrait or "", m.type, fiche, analyse, modeles)
    except ia.ErreurIA as exc:
        raise HTTPException(502, str(exc)) from exc
    db.commit()
    out = MessageOut.model_validate(m)
    out.analyse = analyse
    return out


class MessageUpdate(BaseModel):
    reponse_finale: str | None = None
    statut: StatutMessage | None = None
    article_id: int | None = None


@router.patch("/messages/{message_id}", response_model=MessageOut)
def modifier_message(message_id: int, data: MessageUpdate, db: Db) -> MessageOut:
    m = db.get(Message, message_id)
    if m is None:
        raise HTTPException(404, "Message introuvable.")
    for cle, valeur in data.model_dump(exclude_unset=True).items():
        setattr(m, cle, valeur)
    db.commit()
    a = db.get(Article, m.article_id) if m.article_id else None
    out = MessageOut.model_validate(m)
    out.analyse = _analyse(a, m, get_parametres(db))
    return out


# --- Modèles ----------------------------------------------------------------------------------


class ModeleAnnonceIn(BaseModel):
    nom: str = Field(min_length=1, max_length=120)
    categorie: str | None = None
    structure_titre: str | None = None
    structure_description: str | None = None
    mots_cles: str | None = None


class ModeleAnnonceOut(ModeleAnnonceIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


class ModeleReponseIn(BaseModel):
    nom: str = Field(min_length=1, max_length=120)
    contexte: str = Field(min_length=1, max_length=80)
    texte: str = Field(min_length=1)


class ModeleReponseOut(ModeleReponseIn):
    model_config = ConfigDict(from_attributes=True)
    id: int


def _crud(prefixe: str, modele: Any, entree: type[BaseModel], sortie: type[BaseModel]) -> None:
    @router.get(f"/{prefixe}", response_model=list[sortie], name=f"lister_{prefixe}")  # type: ignore[valid-type]
    def lister(db: Db) -> list[Any]:
        return list(db.scalars(select(modele).order_by(modele.nom)))

    @router.post(f"/{prefixe}", response_model=sortie, status_code=201, name=f"creer_{prefixe}")
    def creer(data: entree, db: Db) -> Any:  # type: ignore[valid-type]
        obj = modele(**data.model_dump())  # type: ignore[attr-defined]
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    @router.put(f"/{prefixe}/{{obj_id}}", response_model=sortie, name=f"modifier_{prefixe}")
    def modifier(obj_id: int, data: entree, db: Db) -> Any:  # type: ignore[valid-type]
        obj = db.get(modele, obj_id)
        if obj is None:
            raise HTTPException(404, "Modèle introuvable.")
        for cle, valeur in data.model_dump().items():  # type: ignore[attr-defined]
            setattr(obj, cle, valeur)
        db.commit()
        return obj

    @router.delete(f"/{prefixe}/{{obj_id}}", status_code=204, name=f"supprimer_{prefixe}")
    def supprimer(obj_id: int, db: Db) -> None:
        obj = db.get(modele, obj_id)
        if obj is None:
            raise HTTPException(404, "Modèle introuvable.")
        db.delete(obj)
        db.commit()


_crud("modeles-annonce", ModeleAnnonce, ModeleAnnonceIn, ModeleAnnonceOut)
_crud("modeles-reponse", ModeleReponse, ModeleReponseIn, ModeleReponseOut)
