"""Retouche des photos d'articles : le vêtement réel, posé sur le tapis de référence.

Principes :
- le vêtement reste strictement identique (couleur, texte des étiquettes, logo, usure, défauts) ;
- le fond est toujours le même tapis (photo de référence dans les paramètres) ;
- la disposition varie d'une photo à l'autre, pour un dressing naturel ;
- une photo de défaut n'est jamais retouchée.
"""

import random
import time
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.logging import log
from app.models import Article, Parametres, PhotoArticle, PhotoVariante
from app.services import images, replicate_client, storage

TYPES = {
    "devant": "Devant",
    "dos": "Dos",
    "etiquette": "Étiquette",
    "logo": "Logo",
    "detail": "Détail",
    "defaut": "Défaut (jamais retouché)",
}
ORDRE_TYPES = list(TYPES)
TYPES_OBLIGATOIRES = ("devant", "dos", "etiquette", "logo")
TYPES_RETOUCHES = ("devant", "dos", "etiquette", "logo", "detail")

# Modèle par défaut selon le type : GPT Image 2 en qualité basse, testé fidèle sur les vues entières,
# les étiquettes et les logos, pour ~0,012 $ la photo. Le bouton « haute qualité » passe par
# Parametres.modele_photos (Nano Banana 2 par défaut).
MODELES_PAR_DEFAUT = {t: "openai/gpt-image-2:low" for t in TYPES_RETOUCHES}


# Modèles proposés dans la comparaison (FLUX.2 et Qwen écartés : fond et vêtement inventés lors des essais).
MODELES_COMPARAISON = [
    "openai/gpt-image-2:low",
    "openai/gpt-image-2:medium",
    "bytedance/seedream-5-lite",
    "google/nano-banana-2",
]


def modele_pour(params: Parametres, type_photo: str, premium: bool = False) -> str:
    if premium:
        return params.modele_photos or "google/nano-banana-2"
    return (params.modeles_photos or {}).get(type_photo) or MODELES_PAR_DEFAUT.get(
        type_photo, "openai/gpt-image-2:low"
    )


FIDELITE = (
    "Keep the garment strictly identical to image 1: same exact color and shade, same fabric texture, "
    "same seams, stitching, ribbing, zipper, drawstrings and proportions; do not add, remove or redraw any "
    "detail, logo, embroidery or printed text, and keep any wear, pilling, marks or stains exactly as they are."
)
REALISME = (
    "Natural smartphone photo taken by a person at home, true-to-life colors, realistic soft shadows, "
    "slightly imperfect framing; no studio lighting, no props, no hands, no added text, no watermark."
)
DISPOSITIONS_VUE_ENTIERE = [
    "sleeves slightly bent inward toward the body",
    "one sleeve folded across the body, the other relaxed along the side",
    "both sleeves relaxed along the sides, slightly asymmetric",
    "sleeves folded behind so the body is the focus",
    "one sleeve slightly raised at an angle, the other bent at the elbow",
    "sleeves gently crossed over the lower body",
]
ROTATIONS = [
    "garment rotated about 5 degrees clockwise",
    "garment rotated about 5 degrees counter-clockwise",
    "garment rotated about 10 degrees clockwise",
    "garment almost straight, very slightly tilted",
    "garment rotated about 8 degrees counter-clockwise",
]
CADRAGES = [
    "garment centered and filling about 75% of the frame",
    "garment slightly off-center toward the top, filling about 80% of the frame",
    "a little more rug visible at the bottom of the frame",
    "garment filling about 70% of the frame, slightly off-center to the left",
]
LUMIERES = [
    "soft natural daylight from a window on the left",
    "soft natural daylight from a window on the right",
    "soft, slightly overcast daylight from above",
]
# Gros plans : jamais plus large que l'original (sinon l'IA invente des parties du vêtement).
ANGLES_GROS_PLAN = [
    "same close-up framing, camera very slightly tilted",
    "same close-up framing, camera slightly rotated",
    "same close-up framing, a touch tighter",
]


def disposition(type_photo: str, rng: random.Random, lumiere: str) -> str:
    if type_photo in ("devant", "dos"):
        return f"{rng.choice(DISPOSITIONS_VUE_ENTIERE)}; {rng.choice(ROTATIONS)}; {rng.choice(CADRAGES)}; {lumiere}"
    return f"{rng.choice(ANGLES_GROS_PLAN)}; {lumiere}"


def description_article(article: Article) -> str:
    morceaux = [article.categorie, article.marque, article.couleur]
    texte = " ".join(m for m in morceaux if m) or article.nom
    return texte.lower()


def construire_prompt(type_photo: str, article: Article, dispo: str, reference_couleur: bool = False) -> str:
    vetement = description_article(article)
    fond = "Image 2 shows the cream shaggy rug to use as background: same cream color and same shaggy pile texture."
    if type_photo in ("devant", "dos"):
        vue = "front" if type_photo == "devant" else "back"
        return (
            f"Image 1 is a real photo of the {vue} of a second-hand garment ({vetement}), on another surface. {fond} "
            f"Create a realistic overhead photo of this exact garment, {vue} side up, lying flat on that rug, seen from "
            f"directly above, for a second-hand clothing listing. The rug fills the entire background. {FIDELITE} "
            "Remove the original floor, feet, shoes and anything that is not the garment. "
            f"Arrangement, laid out naturally like a person would: {dispo}. {REALISME}"
        )
    sujet = {
        "etiquette": "the inside label of the garment. Keep every letter, logo and size marking of the label exactly "
        "as in image 1; do not rewrite, invent, translate or sharpen any text",
        "logo": "the logo or embroidery of the garment. Keep the logo exactly as in image 1: same shape, same colors, "
        "same size and position, same embroidery or print texture",
        "detail": "a detail of the garment",
    }[type_photo]
    couleur = (
        " Image 3 shows the whole garment in good daylight: use it only to match the true fabric color and shade, "
        "so that this close-up has exactly the same color as the other photos of the listing (close-ups are often "
        "darker or lighter than reality)."
        if reference_couleur
        else ""
    )
    return (
        f"Image 1 is a real close-up photo of {sujet}. The garment is a second-hand {vetement}. {fond}{couleur} "
        "Create a realistic close-up photo of exactly the same area of the same garment, where any visible floor or "
        "background is replaced by the cream shaggy rug of image 2. Show only the part of the garment visible in "
        "image 1: do not extend the garment beyond the original crop and never invent a collar, hood, pocket, seam or "
        f"any part that is not visible in image 1. {FIDELITE} Framing: {dispo}. {REALISME}"
    )


def produire(
    db: Session, photo: PhotoArticle, params: Parametres, modele: str, dispo: str
) -> tuple[bytes, str]:
    """Appelle le modèle pour une photo avec une disposition donnée. Renvoie (JPEG, id de prédiction)."""
    if not params.photo_fond:
        raise replicate_client.ErreurReplicate(
            "Ajoute d'abord la photo de ton tapis dans Paramètres → Photos (elle sert de fond à toutes les photos)."
        )
    article = db.get(Article, photo.article_id)
    assert article is not None
    entrees = [
        ("photo.jpg", storage.chemin_absolu(photo.fichier_original).read_bytes()),
        ("tapis.jpg", storage.chemin_absolu(params.photo_fond).read_bytes()),
    ]
    # Gros plan : la photo « devant » sert de référence de couleur (même teinte sur toute l'annonce).
    devant = None
    if photo.type in ("etiquette", "logo", "detail"):
        devant = db.scalar(
            select(PhotoArticle)
            .where(PhotoArticle.article_id == article.id, PhotoArticle.type == "devant")
            .limit(1)
        )
        if devant is not None:
            entrees.append(("devant.jpg", storage.chemin_absolu(devant.fichier_original).read_bytes()))
    prompt = construire_prompt(photo.type, article, dispo, reference_couleur=devant is not None)
    contenu, prediction_id = replicate_client.generer(modele, prompt, entrees)
    return images.en_jpeg(contenu), prediction_id


def prix(modele: str) -> Decimal:
    return Decimal(str(replicate_client.PRIX_PAR_IMAGE.get(modele, 0.07)))


def generer_photo(
    db: Session, photo: PhotoArticle, params: Parametres, lumiere: str, premium: bool = False
) -> None:
    """Génère la version retouchée d'une photo (appel réseau, plusieurs secondes)."""
    if photo.type == "defaut":
        photo.statut, photo.version_choisie = "original", "original"
        db.commit()
        return
    photo.disposition = disposition(photo.type, random.Random(), lumiere)
    modele = modele_pour(params, photo.type, premium)
    contenu, prediction_id = produire(db, photo, params, modele, photo.disposition)
    ancien = photo.fichier_genere
    photo.fichier_genere = storage.ecrire_fichier(
        f"photos/article-{photo.article_id}", f"{photo.type}-ia.jpg", contenu
    )
    if ancien and not db.scalar(select(PhotoVariante.id).where(PhotoVariante.fichier == ancien)):
        storage.supprimer(ancien)
    photo.prediction_id = prediction_id
    photo.modele = modele
    photo.nb_generations += 1
    photo.cout_estime += prix(modele)
    photo.statut, photo.version_choisie, photo.erreur = "genere", "genere", None
    db.commit()


def _marquer_erreur(db: Session, cible: PhotoArticle | PhotoVariante, exc: Exception) -> None:
    db.rollback()
    if db.get(type(cible), cible.id) is None:
        log.info("photo_supprimee_pendant_generation", id=cible.id)  # article supprimé entre-temps
        return
    if isinstance(exc, replicate_client.ErreurReplicate):
        message = str(exc)
    else:  # erreur inattendue : la photo est marquée, les autres continuent
        log.exception("photo_erreur", id=cible.id)
        message = f"Erreur inattendue ({type(exc).__name__}). Réessaie."
    cible.statut, cible.erreur = "erreur", message
    db.commit()


def tache_generation(photo_ids: list[int], premium: bool = False) -> None:
    """Tâche de fond : génère les photos une par une (la limite de débit de Replicate est respectée)."""
    lumiere = random.choice(LUMIERES)  # même lumière pour toutes les photos d'un même lot
    with SessionLocal() as db:
        params = db.get(Parametres, 1) or Parametres(id=1)
        ordre = (
            db.execute(
                select(PhotoArticle.id).where(PhotoArticle.id.in_(photo_ids)).order_by(PhotoArticle.ordre)
            )
            .scalars()
            .all()
        )
        for photo_id in ordre:
            db.expire_all()
            photo = db.get(PhotoArticle, photo_id)
            if photo is None:
                continue  # article supprimé pendant la génération : on n'appelle pas l'API pour rien
            try:
                generer_photo(db, photo, params, lumiere, premium)
            except Exception as exc:
                _marquer_erreur(db, photo, exc)


def tache_comparaison(variante_ids: list[int]) -> None:
    """Tâche de fond : une variante par (photo, modèle). Pour une même photo, tous les modèles reçoivent
    la même disposition, afin que la comparaison ne porte que sur le modèle."""
    with SessionLocal() as db:
        params = db.get(Parametres, 1) or Parametres(id=1)
        for v in db.scalars(
            select(PhotoVariante).where(PhotoVariante.id.in_(variante_ids)).order_by(PhotoVariante.id)
        ):
            photo = db.get(PhotoArticle, v.photo_id)
            assert photo is not None
            debut = time.monotonic()
            try:
                contenu, _ = produire(db, photo, params, v.modele, v.disposition or "")
                nom = f"{photo.type}-{v.modele.replace('/', '-').replace(':', '-')}.jpg"
                v.fichier = storage.ecrire_fichier(
                    f"photos/article-{photo.article_id}/variantes", nom, contenu
                )
                v.statut, v.cout_estime, v.erreur = "genere", prix(v.modele), None
                v.duree_secondes = round(time.monotonic() - debut, 1)
                db.commit()
            except Exception as exc:
                _marquer_erreur(db, v, exc)
