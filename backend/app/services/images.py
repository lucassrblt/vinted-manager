"""Préparation des photos déposées : orientation, taille, format et suppression des métadonnées."""

import io

from PIL import Image, ImageOps, UnidentifiedImageError

TAILLE_MAX = 2048  # côté le plus long envoyé au modèle


class ImageInvalide(ValueError):
    pass


def preparer(contenu: bytes, taille_max: int = TAILLE_MAX) -> bytes:
    """Redresse selon l'EXIF (photos d'iPhone), réduit, convertit en JPEG et retire toutes les
    métadonnées (dont la localisation GPS) avant stockage et envoi à l'API."""
    try:
        source = Image.open(io.BytesIO(contenu))
        source.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ImageInvalide("Image illisible : envoie une photo JPG, PNG ou WEBP.") from exc
    image: Image.Image = ImageOps.exif_transpose(source)
    if image.mode != "RGB":
        image = image.convert("RGB")
    image.thumbnail((taille_max, taille_max), Image.Resampling.LANCZOS)
    sortie = io.BytesIO()
    image.save(sortie, "JPEG", quality=90, optimize=True)  # sans exif= : aucune métadonnée conservée
    return sortie.getvalue()


def en_jpeg(contenu: bytes) -> bytes:
    """Convertit une image générée (souvent PNG) en JPEG compact pour Vinted."""
    return preparer(contenu, taille_max=2304)
