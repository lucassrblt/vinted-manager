"""Chiffrement des secrets stockés en base (mot de passe IMAP) avec Fernet."""

from cryptography.fernet import Fernet, InvalidToken

from app.config import get_settings


class CleManquante(RuntimeError):
    pass


def _fernet() -> Fernet:
    cle = get_settings().fernet_key
    if not cle:
        raise CleManquante(
            "La variable FERNET_KEY n'est pas définie sur le serveur : impossible de chiffrer le mot de passe."
        )
    try:
        return Fernet(cle.encode())
    except ValueError as exc:
        raise CleManquante("La variable FERNET_KEY est invalide (clé Fernet attendue).") from exc


def chiffrer(texte: str) -> str:
    return _fernet().encrypt(texte.encode()).decode()


def dechiffrer(jeton: str) -> str:
    try:
        return _fernet().decrypt(jeton.encode()).decode()
    except InvalidToken as exc:
        raise CleManquante(
            "Impossible de déchiffrer le mot de passe IMAP : FERNET_KEY a changé. Ressaisis le mot de passe."
        ) from exc
