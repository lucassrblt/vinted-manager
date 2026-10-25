"""Republication différenciée (section 10.1).

Tous les 5 jours depuis la dernière publication (réglable), une annonce encore en ligne est republiée :
nouvelle annonce (photos légèrement transformées, texte reformulé et vérifié), publiée, puis l'ancienne
est supprimée. Reportée si un message a été échangé sur l'article il y a moins d'une heure. Avant, une
offre part aux membres qui l'avaient mise en favori sans en avoir reçu.
"""

import io
import math
import random
import re
import shutil
from datetime import datetime, timedelta
from typing import Any

from PIL import Image, ImageEnhance
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, CompteVinted, ConversationVinted, Parametres, TacheVinted
from app.models.enums import EtatArticle, StatutArticle
from app.services import (
    alertes,
    brouillons,
    couleur,
    favoris,
    file_vinted,
    horaires,
    ia,
    photos,
    reglages,
    storage,
    taches,
)
from app.services.marques import normaliser

ESSAIS_REECRITURE = 2
DELTA_E_MAX_PREMIERE = 3.0  # la première photo reste fidèle : écart de couleur imperceptible
MOTS_VIDES = {"le", "la", "les", "un", "une", "des", "de", "du", "sur", "sous", "au", "aux", "et", "en", "tres", "petit", "petite"}  # fmt: skip
ETATS_TEXTE = {
    EtatArticle.NEUF_ETIQUETTE: ("neuf avec etiquette",),
    EtatArticle.NEUF_SANS_ETIQUETTE: ("neuf sans etiquette",),
    EtatArticle.TRES_BON: ("tres bon etat",),
    EtatArticle.BON: ("bon etat",),
    EtatArticle.SATISFAISANT: ("satisfaisant", "etat correct"),
}


# --- Photos -------------------------------------------------------------------------------------


def zoom_necessaire(largeur: int, hauteur: int, angle_deg: float) -> float:
    """Part de l'image à rogner pour qu'aucun coin vide de la rotation ne reste visible."""
    t = math.radians(abs(angle_deg))
    c, s = math.cos(t), math.sin(t)
    k = min(largeur / (largeur * c + hauteur * s), hauteur / (largeur * s + hauteur * c))
    return 1 - k


def transformer(
    contenu: bytes, rng: random.Random, sens: int, r: dict[str, Any], premiere: bool = False
) -> tuple[bytes, dict[str, float]]:
    """Rotation légère (sens donné), zoom qui masque les coins, luminosité un peu plus basse, réencodage
    JPEG sans métadonnées. Renvoie le JPEG et les paramètres tirés."""
    source = Image.open(io.BytesIO(contenu)).convert("RGB")
    largeur, hauteur = source.size
    angle = rng.uniform(r["rotation_min"], r["rotation_max"]) * sens
    zoom = max(
        rng.uniform(r["zoom_min"], r["zoom_max"]) / 100, zoom_necessaire(largeur, hauteur, angle) + 0.002
    )
    luminosite = rng.uniform(r["luminosite_min"], r["luminosite_max"]) / 100
    qualite = rng.randint(int(r["qualite_min"]), int(r["qualite_max"]))
    tournee = source.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False)
    garde_l, garde_h = largeur * (1 - zoom), hauteur * (1 - zoom)
    gauche, haut = (largeur - garde_l) / 2, (hauteur - garde_h) / 2
    recadree = tournee.crop((round(gauche), round(haut), round(gauche + garde_l), round(haut + garde_h)))
    agrandie = recadree.resize((largeur, hauteur), Image.Resampling.LANCZOS)

    def encoder(baisse: float) -> bytes:
        image = ImageEnhance.Brightness(agrandie).enhance(1 - baisse)
        sortie = io.BytesIO()
        image.save(sortie, "JPEG", quality=qualite, optimize=True)  # sans exif : aucune métadonnée
        return sortie.getvalue()

    resultat = encoder(luminosite)
    if premiere:
        # La baisse de luminosité ne doit pas changer la couleur perçue de la première photo.
        for baisse in (luminosite, luminosite / 2, 0.0):
            resultat = encoder(baisse)
            if couleur.ecart(contenu, resultat) <= DELTA_E_MAX_PREMIERE:
                luminosite = baisse
                break
    return resultat, {
        "angle": round(angle, 2),
        "zoom": round(zoom * 100, 2),
        "luminosite": round(luminosite * 100, 2),
        "qualite": qualite,
    }


def photos_reference(db: Session, article: Article, params: Parametres) -> list[bytes]:
    """Photos publiées la première fois (jamais une version déjà transformée), dans l'ordre Vinted."""
    return [brouillons.contenu_publie(p, params) for p in photos.photos_ordonnees(db, article.id)]


# --- Texte ---------------------------------------------------------------------------------------


def _mots(texte: str) -> list[str]:
    return [m for m in normaliser(texte).replace("-", " ").split() if len(m) >= 3 and m not in MOTS_VIDES]


def manquants(article: Article, titre: str, description: str) -> list[str]:
    """Informations obligatoires absentes d'une réécriture : marque, taille, état, défauts, matière, mots-clés."""
    tout = f" {normaliser(titre + ' ' + description).replace('-', ' ')} "
    absents = []
    if article.marque and f" {normaliser(article.marque).replace('-', ' ')} " not in tout:
        absents.append("marque")
    if article.taille and not re.search(rf"\b{re.escape(normaliser(article.taille))}\b", tout):
        absents.append("taille")
    if article.etat in ETATS_TEXTE and not any(e in tout for e in ETATS_TEXTE[EtatArticle(article.etat)]):
        absents.append("état")
    if article.defauts:
        mots = _mots(article.defauts)
        if mots and sum(m in tout for m in mots) / len(mots) < 0.7:
            absents.append("défauts")
    if article.matiere and not all(m in tout for m in _mots(re.sub(r"[\d%]", " ", article.matiere))):
        absents.append("matière")
    for mot_cle in (article.mots_cles_annonce or "").split(","):
        if mot_cle.strip() and f" {normaliser(mot_cle.strip())} " not in tout:
            absents.append(f"mot-clé « {mot_cle.strip()} »")
    return absents


def texte_republication(db: Session, compte: CompteVinted, article: Article) -> tuple[str, str]:
    """Titre et description reformulés et vérifiés ; à défaut, l'annonce actuelle telle quelle."""
    titre = article.titre_annonce or article.nom
    description = article.description_annonce or ""
    fiche = {
        "marque": article.marque, "modele": article.modele, "categorie": article.categorie, "taille": article.taille,
        "couleur": article.couleur, "etat": article.etat, "matiere": article.matiere, "defauts": article.defauts,
    }  # fmt: skip
    mots_cles = [m.strip() for m in (article.mots_cles_annonce or "").split(",") if m.strip()]
    for essai in range(ESSAIS_REECRITURE):
        try:
            r = ia.reecrire_annonce(titre, description, fiche, mots_cles, essai)
        except ia.ErreurIA as exc:
            alertes.journaliser(
                db,
                compte,
                "republication",
                f"{article.nom} : réécriture impossible ({exc}).",
                article_id=article.id,
            )
            break
        absents = manquants(article, r.titre, r.description)
        if not absents and r.description:
            return r.titre, r.description
        alertes.journaliser(
            db,
            compte,
            "republication",
            f"{article.nom} : réécriture refusée, manque {', '.join(absents)}.",
            article_id=article.id,
        )
    return titre, description


# --- Planification -------------------------------------------------------------------------------


def derniere_publication(article: Article) -> datetime | None:
    return article.derniere_publication_le or article.date_publication


def conversation_active(db: Session, compte: CompteVinted, article: Article) -> bool:
    minutes = reglages.du_compte(compte)["republication"]["conversation_active_minutes"]
    limite = horaires.maintenant() - timedelta(minutes=minutes)
    return bool(
        db.scalar(
            select(ConversationVinted.id)
            .where(
                ConversationVinted.article_id == article.id, ConversationVinted.dernier_message_le > limite
            )
            .limit(1)
        )
    )


def _en_attente(
    db: Session, compte: CompteVinted, types: tuple[str, ...], article_id: int | None = None
) -> bool:
    q = select(TacheVinted.id).where(
        TacheVinted.compte_id == compte.id,
        TacheVinted.type.in_(types),
        TacheVinted.statut.in_(("a_faire", "a_valider", "en_cours")),
    )
    if article_id is not None:
        q = q.where(TacheVinted.article_id == article_id)
    return bool(db.scalar(q.limit(1)))


def candidats(db: Session, compte: CompteVinted) -> list[Article]:
    cadence = timedelta(days=reglages.du_compte(compte)["republication"]["cadence_jours"])
    maintenant = horaires.maintenant()
    liste = [
        a
        for a in db.scalars(
            select(Article).where(
                Article.compte_id == compte.id,
                Article.statut == StatutArticle.EN_LIGNE,
                Article.vinted_item_id.is_not(None),
            )
        )
        if (d := derniere_publication(a)) is not None and maintenant - d >= cadence
    ]
    return sorted(liste, key=lambda a: derniere_publication(a) or maintenant)


def preparer(db: Session, compte: CompteVinted, article: Article, params: Parametres) -> TacheVinted | None:
    """Photos transformées et texte vérifié, puis la tâche (dans 0 à 20 min). None si pas encore possible."""
    if not photos.photos_ordonnees(db, article.id):
        if article.vinted_photos and not _en_attente(db, compte, ("photos_reference",), article.id):
            taches.creer(db, compte, "photos_reference", {"urls": article.vinted_photos[:20]}, article.id)
            alertes.journaliser(
                db,
                compte,
                "republication",
                f"{article.nom} : photos de référence à télécharger.",
                article_id=article.id,
            )
        return None
    if (
        not (article.description_annonce or "").strip()
        or article.etat not in brouillons.CONDITION_IDS
        or not article.prix_vente_cible
    ):
        alertes.journaliser(
            db,
            compte,
            "republication",
            f"{article.nom} : description, état ou prix manquant, republication impossible.",
            "alerte",
            article.id,
        )
        article.derniere_publication_le = (
            horaires.maintenant()
        )  # on ne réessaie pas avant la prochaine échéance
        return None
    titre, description = texte_republication(db, compte, article)
    r = reglages.du_compte(compte)["republication"]
    rng = random.Random()
    sens = -1 if article.republications % 2 else 1  # sens de rotation alterné d'une republication à l'autre
    tache = taches.creer(
        db, compte, "republication", {}, article.id, horaires.maintenant() + horaires.delai(0, 20 * 60)
    )
    fichiers, reglages_tires = [], []
    for i, contenu in enumerate(photos_reference(db, article, params)):
        jpeg, tirage = transformer(contenu, rng, sens, r, premiere=i == 0)
        fichiers.append(storage.ecrire_fichier(f"republication/tache-{tache.id}", f"{i:02d}.jpg", jpeg))
        reglages_tires.append(tirage)
    liste = photos.photos_ordonnees(db, article.id)
    ai_photo = article.ai_photo_declare if article.ai_photo_declare is not None else (
        brouillons.ai_photo(liste, params) if not article.importe_vinted else True
    )  # fmt: skip
    assert article.prix_vente_cible is not None and article.etat is not None
    tache.payload = {
        "ancien_item_id": article.vinted_item_id,
        "titre": titre,
        "description": description,
        "prix": brouillons.prix_texte(article.prix_vente_cible),
        "marque": article.marque,
        "taille": article.taille,
        "condition_id": brouillons.CONDITION_IDS[EtatArticle(article.etat)],
        "couleur": article.couleur,
        "matiere": article.matiere,
        "categorie": article.categorie,
        "package_size_id": brouillons.package_size_id(article.categorie),
        "ai_photo": bool(ai_photo),
        "photos": [{"index": i, "fichier": f} for i, f in enumerate(fichiers)],
        "transformations": reglages_tires,
    }
    alertes.journaliser(
        db, compte, "republication", f"Republication programmée : {article.nom}.", article_id=article.id
    )
    return tache


def planifier(db: Session) -> int:
    """Toutes les 30 min : au plus une republication programmée par compte (jamais en rafale)."""
    params = db.get(Parametres, 1)
    if params is None:
        params = Parametres(id=1)
        db.add(params)
        db.flush()
    if not params.automatisation_active:
        return 0
    n = 0
    for compte in db.scalars(select(CompteVinted).where(CompteVinted.jeton_extension_hash.is_not(None))):
        if not brouillons.compte_pret(compte) or not reglages.module_actif(compte, "republication"):
            continue
        if not horaires.actif(compte) or _en_attente(db, compte, ("republication", "photos_reference")):
            continue
        for article in candidats(db, compte):
            if conversation_active(db, compte, article) or _en_attente(
                db, compte, ("relance_favori",), article.id
            ):
                continue  # nouvel essai dans 30 min
            if reglages.module_actif(compte, "favoris") and favoris.relancer_avant_republication(
                db, compte, article
            ):
                break  # les offres aux favoris partent d'abord ; la republication suivra
            if preparer(db, compte, article, params) is not None:
                n += 1
                break
    alertes.valider(db)
    return n


@file_vinted.avant("republication")
def _avant(db: Session, compte: CompteVinted, tache: TacheVinted) -> datetime | None:
    """Juste avant l'exécution : conversation récente sur l'article → report de 30 min."""
    article = db.get(Article, tache.article_id) if tache.article_id else None
    if article is None or article.statut != StatutArticle.EN_LIGNE:
        tache.statut, tache.erreur = "annulee", "Article plus en ligne."
        return None
    if conversation_active(db, compte, article):
        return horaires.maintenant() + timedelta(minutes=30)
    return None


def _nettoyer(tache: TacheVinted) -> None:
    dossier = storage.chemin_absolu(f"republication/tache-{tache.id}")
    if dossier.exists():
        shutil.rmtree(dossier, ignore_errors=True)


@file_vinted.apres("republication")
def _apres(db: Session, compte: CompteVinted, tache: TacheVinted, ok: bool) -> None:
    article = db.get(Article, tache.article_id) if tache.article_id else None
    r = tache.resultat or {}
    nouvel = r.get("nouvel_item_id")
    _nettoyer(tache)
    if article is not None and nouvel:
        article.vinted_item_id = article.vinted_draft_id = int(nouvel)
        article.derniere_publication_le = horaires.maintenant()
        article.republications += 1
        if tache.payload.get("titre"):
            article.titre_annonce = str(tache.payload["titre"])[:120]
            article.description_annonce = str(tache.payload.get("description") or article.description_annonce)
    nom = article.nom if article else str(tache.payload.get("titre"))
    if ok:
        alertes.journaliser(
            db, compte, "republication", f"Republiée : {nom} (annonce {nouvel}).", article_id=tache.article_id
        )
    elif nouvel:
        alertes.alerter(
            db, compte, "tache_erreur", "Ancienne annonce non supprimée",
            f"{nom} : nouvelle annonce {nouvel} en ligne, mais l'ancienne ({tache.payload.get('ancien_item_id')}) "
            f"est toujours là. Supprime-la à la main. {tache.erreur or ''}",
            article_id=tache.article_id,
        )  # fmt: skip
    else:
        alertes.alerter(
            db,
            compte,
            "tache_erreur",
            "Republication en échec",
            f"{nom} : {tache.erreur or ''} L'ancienne annonce reste en ligne.",
            article_id=tache.article_id,
        )


@file_vinted.apres("photos_reference")
def _apres_photos(db: Session, compte: CompteVinted, tache: TacheVinted, ok: bool) -> None:
    if not ok:
        alertes.journaliser(
            db,
            compte,
            "republication",
            f"Photos de référence non téléchargées : {tache.erreur}",
            "erreur",
            tache.article_id,
        )
