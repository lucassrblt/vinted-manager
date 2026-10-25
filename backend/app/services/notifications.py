"""Point d'entrée unique des notifications (push Web vers les appareils abonnés).

Pendant le traitement d'un mail, les notifications sont mises en attente sur la session SQLAlchemy
puis envoyées après le commit : un envoi lent ou en échec ne touche jamais la transaction.
"""

from sqlalchemy.orm import Session

from app.logging import log
from app.services import push, telegram

CLE = "notifications_en_attente"
# Notifications des mails relayées aussi sur Telegram (chat du compte qui a reçu le mail).
TYPES_TELEGRAM = {"vente": "vente", "litige": "litige"}


def notifier(
    db: Session,
    type_notification: str,
    titre: str,
    url: str | None = None,
    corps: str = "",
    compte_id: int | None = None,
) -> None:
    log.info("notification", type=type_notification, url=url)
    db.info.setdefault(CLE, []).append((type_notification, titre, corps, url or "/"))
    if type_notification in TYPES_TELEGRAM:
        from app.models import CompteVinted
        from app.services import alertes  # import local : alertes dépend de ce module

        compte = db.get(CompteVinted, compte_id) if compte_id else None
        texte = titre + (f"\n{corps}" if corps else "")
        alertes.telegram_pour(db, compte, TYPES_TELEGRAM[type_notification], texte)


def envoyer_en_attente(db: Session) -> None:
    for type_notification, titre, corps, url in db.info.pop(CLE, []):
        try:
            push.envoyer(db, type_notification, titre, corps, url)
        except Exception:  # une notification ne doit jamais faire échouer le traitement
            log.exception("notification_erreur")
    telegram.envoyer_en_attente(db)


def annuler_en_attente(db: Session) -> None:
    db.info.pop(CLE, None)
    telegram.annuler_en_attente(db)
