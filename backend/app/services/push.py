"""Notifications Web Push (VAPID), envoyées à tous les appareils abonnés.

Clés : VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY (base64url, voir `python -m app.cli vapid-keys`).
"""

import base64
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pywebpush import WebPushException, webpush
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging import log
from app.models import AbonnementPush, Parametres

TYPES = {
    "vente": "Nouvelle vente détectée",
    "litige": "Nouveau litige",
    "offre": "Nouvelle offre",
    "message": "Nouveau message",
    "favori": "Article mis en favori",
    "non_classe": "Mail Vinted non reconnu",
    "rappel_envois": "Rappel de 9 h : colis à envoyer",
}


def configure() -> bool:
    s = get_settings()
    return bool(s.vapid_public_key and s.vapid_private_key)


def _b64(octets: bytes) -> str:
    return base64.urlsafe_b64encode(octets).rstrip(b"=").decode()


def generer_cles() -> tuple[str, str]:
    """(publique, privée) au format attendu par le navigateur et pywebpush."""
    cle = ec.generate_private_key(ec.SECP256R1())
    privee = cle.private_numbers().private_value.to_bytes(32, "big")
    publique = cle.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return _b64(publique), _b64(privee)


def type_actif(db: Session, type_notification: str) -> bool:
    params = db.get(Parametres, 1)
    prefs = (params.notifications if params else None) or {}
    return bool(prefs.get(type_notification, True))


def envoyer_a(abonnement: AbonnementPush, titre: str, corps: str, url: str) -> bool:
    """Envoie à un appareil. Renvoie False si l'abonnement est expiré (à supprimer)."""
    s = get_settings()
    try:
        webpush(
            subscription_info={
                "endpoint": abonnement.endpoint,
                "keys": {"p256dh": abonnement.p256dh, "auth": abonnement.auth},
            },
            data=json.dumps({"titre": titre, "corps": corps, "url": url}),
            vapid_private_key=s.vapid_private_key,
            vapid_claims={"sub": s.vapid_subject},
            timeout=10,
            ttl=24 * 3600,
        )
    except WebPushException as exc:
        statut = exc.response.status_code if exc.response is not None else None
        if statut in (404, 410):
            return False
        log.warning("push_erreur", statut=statut)
    except Exception as exc:  # réseau, clé invalide : la notification ne doit jamais casser le traitement
        log.warning("push_erreur", erreur=type(exc).__name__)
    return True


def envoyer(
    db: Session, type_notification: str, titre: str, corps: str = "", url: str = "/", forcer: bool = False
) -> int:
    """Envoie à tous les appareils si ce type est activé. Renvoie le nombre d'appareils notifiés."""
    if not configure() or (not forcer and not type_actif(db, type_notification)):
        return 0
    envoyes = 0
    for abonnement in db.scalars(select(AbonnementPush)).all():
        if envoyer_a(abonnement, titre, corps, url):
            envoyes += 1
        else:
            db.delete(abonnement)  # appareil désabonné ou expiré
    db.commit()
    return envoyes
