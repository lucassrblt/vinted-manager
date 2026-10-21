"""Point d'entrée unique des notifications. Les notifications push Web arrivent à l'étape 4 :
d'ici là, l'événement est seulement journalisé (sans données sensibles)."""

from app.logging import log


def notifier(type_notification: str, titre: str, url: str | None = None) -> None:
    log.info("notification", type=type_notification, url=url)
