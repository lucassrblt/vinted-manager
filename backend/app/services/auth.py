"""Authentification mono-utilisateur : argon2, sessions en base, anti-bruteforce."""

import hashlib
import secrets
from datetime import timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import utcnow
from app.models import SessionUtilisateur, TentativeConnexion, Utilisateur

_hasher = PasswordHasher()
COOKIE_SESSION = "vm_session"


class CompteBloque(Exception):
    def __init__(self, minutes_restantes: int) -> None:
        self.minutes_restantes = minutes_restantes


def hasher_mot_de_passe(mot_de_passe: str) -> str:
    return _hasher.hash(mot_de_passe)


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _verifier_blocage(db: Session, email: str) -> None:
    s = get_settings()
    duree = timedelta(minutes=s.login_lock_minutes)
    echecs = db.scalars(
        select(TentativeConnexion.date)
        .where(
            TentativeConnexion.email == email,
            TentativeConnexion.succes.is_(False),
            TentativeConnexion.date >= utcnow() - 2 * duree,
        )
        .order_by(TentativeConnexion.date.desc())
    ).all()
    if not echecs:
        return
    # Les tentatives pendant le blocage ne sont pas enregistrées : le dernier échec est
    # celui qui a déclenché le blocage, qui dure `duree` à partir de lui.
    dernier = echecs[0]
    recents = [d for d in echecs if d >= dernier - duree]
    fin_blocage = dernier + duree
    if len(recents) >= s.login_max_failures and utcnow() < fin_blocage:
        restant = fin_blocage - utcnow()
        raise CompteBloque(int(restant.total_seconds() // 60) + 1)


def authentifier(db: Session, email: str, mot_de_passe: str, ip: str | None) -> Utilisateur | None:
    email = email.strip().lower()
    _verifier_blocage(db, email)
    user = db.scalar(select(Utilisateur).where(Utilisateur.email == email))
    ok = False
    if user is not None:
        try:
            ok = _hasher.verify(user.mot_de_passe_hash, mot_de_passe)
        except (VerifyMismatchError, InvalidHashError):
            ok = False
    else:
        # Temps de réponse comparable que l'email existe ou non.
        _hasher.hash(mot_de_passe)
    db.add(TentativeConnexion(email=email, ip=ip, succes=ok))
    if ok:
        db.execute(
            delete(TentativeConnexion).where(
                TentativeConnexion.email == email, TentativeConnexion.succes.is_(False)
            )
        )
    db.commit()
    return user if ok else None


def creer_session(db: Session, user: Utilisateur, user_agent: str | None) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        SessionUtilisateur(
            utilisateur_id=user.id,
            token_hash=_hash_token(token),
            expires_at=utcnow() + timedelta(days=get_settings().session_days),
            user_agent=(user_agent or "")[:255],
        )
    )
    db.commit()
    return token


def session_valide(db: Session, token: str) -> SessionUtilisateur | None:
    """Renvoie la session si elle est valide et prolonge sa durée (renouvellement à l'usage)."""
    session = db.scalar(select(SessionUtilisateur).where(SessionUtilisateur.token_hash == _hash_token(token)))
    if session is None or session.expires_at <= utcnow():
        return None
    nouvelle_expiration = utcnow() + timedelta(days=get_settings().session_days)
    # Écriture au plus une fois par heure pour éviter un UPDATE à chaque requête.
    if nouvelle_expiration - session.expires_at > timedelta(hours=1):
        session.expires_at = nouvelle_expiration
        db.commit()
    return session


def supprimer_session(db: Session, token: str) -> None:
    db.execute(delete(SessionUtilisateur).where(SessionUtilisateur.token_hash == _hash_token(token)))
    db.commit()


def nettoyer_sessions(db: Session) -> None:
    db.execute(delete(SessionUtilisateur).where(SessionUtilisateur.expires_at <= utcnow()))
    db.execute(delete(TentativeConnexion).where(TentativeConnexion.date <= utcnow() - timedelta(days=7)))
    db.commit()


def nb_utilisateurs(db: Session) -> int:
    return db.scalar(select(func.count(Utilisateur.id))) or 0
