"""Authentification de l'extension Chrome (un jeton par compte Vinted) et contrôle du compte connecté."""

import hashlib
import hmac
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import CompteVinted
from app.services import alertes


def hasher(jeton: str) -> str:
    return hashlib.sha256(jeton.encode()).hexdigest()


def generer_jeton(compte: CompteVinted) -> str:
    """Nouveau jeton (affiché une seule fois) ; l'ancien cesse de fonctionner."""
    jeton = "vmx_" + secrets.token_urlsafe(32)
    compte.jeton_extension_hash = hasher(jeton)
    return jeton


def compte_du_jeton(db: Session, jeton: str | None) -> CompteVinted | None:
    """Comparaison en temps constant avec chaque jeton enregistré (quelques comptes seulement)."""
    if not jeton:
        return None
    empreinte = hasher(jeton)
    trouve = None
    for compte in db.scalars(select(CompteVinted).where(CompteVinted.jeton_extension_hash.is_not(None))):
        assert compte.jeton_extension_hash is not None
        if hmac.compare_digest(compte.jeton_extension_hash, empreinte):
            trouve = compte
    return trouve


def battement(
    db: Session, compte: CompteVinted, vinted_user_id: int | None, login: str | None, version: str | None
) -> None:
    """Signal de vie de l'extension, avec le compte Vinted connecté dans le profil Chrome."""
    compte.extension_vue_le = utcnow()
    compte.extension_version = (version or "")[:40] or None
    if vinted_user_id is None:
        return
    nouveau = vinted_user_id != compte.vinted_user_id_vu
    compte.vinted_user_id_vu = vinted_user_id
    compte.vinted_login_vu = (login or "")[:120] or None
    if nouveau and compte.vinted_user_id is not None and vinted_user_id != compte.vinted_user_id:
        alertes.alerter(
            db,
            compte,
            "mauvais_compte",
            "Mauvais compte connecté dans ce profil",
            f"Vinted indique {login or vinted_user_id} ({vinted_user_id}), attendu {compte.vinted_user_id}. "
            "Aucune action n'est faite tant que ce n'est pas corrigé.",
        )
