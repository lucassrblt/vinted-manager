"""Heures actives (Europe/Paris) et délais aléatoires « humains » entre les actions sur Vinted."""

import random
import re
from datetime import UTC, datetime, time, timedelta

from app.db import utcnow
from app.models import CompteVinted
from app.services import reglages
from app.services.stats import tz


def maintenant() -> datetime:
    """Heure courante (UTC) : point unique, figé dans les tests."""
    return utcnow()


def local(quand: datetime | None = None) -> datetime:
    return (quand or maintenant()).astimezone(tz())


def bornes(compte: CompteVinted) -> tuple[int, int]:
    h = reglages.du_compte(compte)["heures"]
    return int(h["debut"]), int(h["fin"])


def actif(compte: CompteVinted, quand: datetime | None = None) -> bool:
    debut, fin = bornes(compte)
    return debut <= local(quand).hour < fin


def prochaine_ouverture(compte: CompteVinted, quand: datetime | None = None) -> datetime:
    """Début de la prochaine plage active (maintenant si on y est déjà)."""
    maintenant = local(quand)
    debut, _ = bornes(compte)
    if actif(compte, maintenant):
        return maintenant
    jour = maintenant.date() if maintenant.hour < debut else maintenant.date() + timedelta(days=1)
    return datetime.combine(jour, time(debut), tzinfo=tz())


def debut_du_jour(quand: datetime | None = None) -> datetime:
    """Minuit (heure de Paris) du jour de `quand`."""
    return datetime.combine(local(quand).date(), time(0), tzinfo=tz())


def debut_heure_suivante(quand: datetime | None = None) -> datetime:
    return local(quand).replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)


def ouverture_du_lendemain(compte: CompteVinted, quand: datetime | None = None) -> datetime:
    debut, _ = bornes(compte)
    return datetime.combine(local(quand).date() + timedelta(days=1), time(debut), tzinfo=tz())


def delai(min_s: float, max_s: float, rng: random.Random | None = None) -> timedelta:
    return timedelta(seconds=(rng or random).uniform(min_s, max_s))


def delai_reponse(compte: CompteVinted, quand: datetime | None = None) -> timedelta:
    """Réponse à un acheteur : 20 à 60 s en journée, 5 à 15 min la nuit."""
    return delai(20, 60) if actif(compte, quand) else delai(5 * 60, 15 * 60)


def date_vinted(texte: object) -> datetime | None:
    """Date ISO de Vinted (« 2026-10-25T10:27:26.518581397Z ») : nanosecondes tronquées, UTC par défaut."""
    if not isinstance(texte, str) or not texte:
        return None
    propre = re.sub(r"(\.\d{6})\d+", r"\1", texte.strip()).replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(propre)
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=UTC)
