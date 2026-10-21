"""Client minimal de l'API Replicate (envoi de fichiers, prédiction, attente du résultat)."""

import time
from typing import Any

import httpx

from app.config import get_settings
from app.logging import log

API = "https://api.replicate.com/v1"
ATTENTE_MAX = 240  # secondes
TENTATIVES_429 = 6

# Prix indicatifs par image générée (USD), pour estimer le coût. Vérifiés le 21/10/2026.
PRIX_PAR_IMAGE = {
    "google/nano-banana-2": 0.067,
    "bytedance/seedream-5-lite": 0.035,
    "bytedance/seedream-4.5": 0.04,
    "black-forest-labs/flux-2-pro": 0.03,
    "qwen/qwen-image-edit-plus": 0.03,
}
# Nom du champ des images d'entrée selon le modèle
CHAMP_IMAGES = {"black-forest-labs/flux-2-pro": "input_images", "qwen/qwen-image-edit-plus": "image"}


class ErreurReplicate(Exception):
    """Erreur affichable telle quelle."""


def _entetes() -> dict[str, str]:
    jeton = get_settings().replicate_api_token
    if not jeton:
        raise ErreurReplicate(
            "La génération de photos n'est pas configurée : REPLICATE_API_TOKEN manquant sur le serveur."
        )
    return {"Authorization": f"Bearer {jeton}"}


def _verifier(r: httpx.Response) -> dict[str, Any]:
    if r.status_code == 401:
        raise ErreurReplicate("Token Replicate refusé : vérifie REPLICATE_API_TOKEN.")
    if r.status_code == 402:
        raise ErreurReplicate("Crédit Replicate épuisé : ajoute du crédit sur replicate.com (Billing).")
    if r.status_code >= 400:
        try:
            detail = r.json().get("detail") or r.text
        except ValueError:
            detail = r.text
        raise ErreurReplicate(f"Replicate a refusé la demande ({r.status_code}) : {str(detail)[:200]}")
    data: dict[str, Any] = r.json()
    return data


def envoyer_fichier(client: httpx.Client, nom: str, contenu: bytes) -> str:
    r = client.post(
        f"{API}/files", headers=_entetes(), files={"content": (nom, contenu, "image/jpeg")}, timeout=60
    )
    return str(_verifier(r)["urls"]["get"])


def entree_modele(modele: str, prompt: str, images: list[str]) -> dict[str, Any]:
    entree: dict[str, Any] = {
        "prompt": prompt,
        CHAMP_IMAGES.get(modele, "image_input"): images,
        "aspect_ratio": "3:4",
    }
    if modele.startswith("google/nano-banana"):
        entree |= {"resolution": "1K", "output_format": "jpg"}  # 1K : prix de base, suffisant pour Vinted
    elif modele.startswith("bytedance/seedream"):
        entree |= {"size": "2K", "max_images": 1}
    else:
        entree |= {"output_format": "jpg"}
    return entree


def generer(modele: str, prompt: str, images: list[tuple[str, bytes]]) -> tuple[bytes, str]:
    """Lance une génération et renvoie (image produite, id de la prédiction)."""
    with httpx.Client() as client:
        urls = [envoyer_fichier(client, nom, contenu) for nom, contenu in images]
        corps = {"input": entree_modele(modele, prompt, urls)}
        for tentative in range(TENTATIVES_429):
            r = client.post(f"{API}/models/{modele}/predictions", headers=_entetes(), json=corps, timeout=60)
            if r.status_code != 429:
                break
            # Compte avec peu de crédit : 6 créations par minute, une à la fois.
            attente = float(r.json().get("retry_after") or 10) + 1
            log.info("replicate_limite", attente=attente, tentative=tentative)
            time.sleep(attente)
        prediction = _verifier(r)
        debut = time.monotonic()
        while prediction.get("status") not in ("succeeded", "failed", "canceled"):
            if time.monotonic() - debut > ATTENTE_MAX:
                raise ErreurReplicate("La génération prend trop de temps. Réessaie.")
            time.sleep(2)
            prediction = _verifier(client.get(prediction["urls"]["get"], headers=_entetes(), timeout=60))
        if prediction["status"] != "succeeded":
            raise ErreurReplicate(
                f"La génération a échoué : {str(prediction.get('error') or prediction['status'])[:200]}"
            )
        sortie = prediction["output"]
        url = sortie[0] if isinstance(sortie, list) else sortie
        image = client.get(url, timeout=120)
        image.raise_for_status()
        return image.content, str(prediction["id"])
