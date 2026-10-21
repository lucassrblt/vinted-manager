"""Stockage des fichiers sur le volume /data. La base ne garde que le chemin relatif."""

import re
import secrets
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.config import get_settings

TYPES_PREUVES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
}
# Signatures de fichiers : on ne fait pas confiance au Content-Type envoyé par le navigateur.
SIGNATURES: dict[str, tuple[bytes, ...]] = {
    "application/pdf": (b"%PDF",),
    "image/jpeg": (b"\xff\xd8\xff",),
    "image/png": (b"\x89PNG\r\n\x1a\n",),
}


def racine() -> Path:
    return get_settings().data_dir


def chemin_absolu(relatif: str) -> Path:
    chemin = (racine() / relatif).resolve()
    if not chemin.is_relative_to(racine().resolve()):
        raise HTTPException(400, "Chemin de fichier invalide.")
    return chemin


def nom_sur(nom: str) -> str:
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", nom).strip("._") or "fichier"
    return base[:80]


def _signature_ok(mime: str, debut: bytes) -> bool:
    if mime == "image/heic":
        return debut[4:8] == b"ftyp"
    if mime == "image/webp":
        return debut.startswith(b"RIFF") and debut[8:12] == b"WEBP"
    return any(debut.startswith(sig) for sig in SIGNATURES.get(mime, ()))


async def enregistrer_upload(
    fichier: UploadFile, dossier: str, types: dict[str, str]
) -> tuple[str, int, str]:
    """Valide type et taille puis écrit le fichier. Renvoie (chemin relatif, taille, mime)."""
    mime = (fichier.content_type or "").lower()
    if mime not in types:
        raise HTTPException(415, "Type de fichier non accepté (PDF, JPG, PNG, WEBP ou HEIC uniquement).")
    max_octets = get_settings().max_upload_mb * 1024 * 1024
    contenu = await fichier.read(max_octets + 1)
    if len(contenu) > max_octets:
        raise HTTPException(413, f"Fichier trop volumineux (maximum {get_settings().max_upload_mb} Mo).")
    if not contenu:
        raise HTTPException(400, "Le fichier est vide.")
    if not _signature_ok(mime, contenu[:16]):
        raise HTTPException(415, "Le contenu du fichier ne correspond pas à son type.")
    nom = f"{secrets.token_hex(8)}_{nom_sur(Path(fichier.filename or 'fichier').stem)}{types[mime]}"
    relatif = f"{dossier}/{nom}"
    cible = chemin_absolu(relatif)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(contenu)
    return relatif, len(contenu), mime


def supprimer(relatif: str) -> None:
    chemin = chemin_absolu(relatif)
    if chemin.exists():
        chemin.unlink()
