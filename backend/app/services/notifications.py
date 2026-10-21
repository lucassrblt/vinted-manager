"""Point d'entrée unique des notifications (push Web vers les appareils abonnés).

Pendant le traitement d'un mail, les notifications sont mises en attente sur la session SQLAlchemy
puis envoyées après le commit : un envoi lent ou en échec ne touche jamais la transaction.
"""

from sqlalchemy.orm import Session

from app.logging import log
from app.services import push

CLE = "notifications_en_attente"


def notifier(
    db: Session, type_notification: str, titre: str, url: str | None = None, corps: str = ""
) -> None:
    log.info("notification", type=type_notification, url=url)
    db.info.setdefault(CLE, []).append((type_notification, titre, corps, url or "/"))


def envoyer_en_attente(db: Session) -> None:
    for type_notification, titre, corps, url in db.info.pop(CLE, []):
        try:
            push.envoyer(db, type_notification, titre, corps, url)
        except Exception:  # une notification ne doit jamais faire échouer le traitement
            log.exception("notification_erreur")


def annuler_en_attente(db: Session) -> None:
    db.info.pop(CLE, None)
