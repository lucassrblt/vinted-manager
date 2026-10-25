"""Alertes de l'automatisation Vinted : journal, notification push (et Telegram à partir de la phase 2).

Comme `notifications.notifier`, l'envoi est mis en attente sur la session et part après le commit
(`valider`) : un envoi lent ou en échec ne touche jamais la transaction.
"""

from sqlalchemy.orm import Session

from app.logging import log
from app.models import CompteVinted, JournalVinted
from app.services.notifications import envoyer_en_attente, notifier


def journaliser(
    db: Session,
    compte: CompteVinted | None,
    type_entree: str,
    message: str,
    niveau: str = "info",
    article_id: int | None = None,
) -> JournalVinted:
    entree = JournalVinted(
        compte_id=compte.id if compte else None,
        niveau=niveau,
        type=type_entree[:40],
        message=message,
        article_id=article_id,
    )
    db.add(entree)
    log.info("journal_vinted", compte=entree.compte_id, type=type_entree, niveau=niveau)
    return entree


def alerter(
    db: Session,
    compte: CompteVinted | None,
    type_alerte: str,
    titre: str,
    corps: str = "",
    url: str = "/parametres?onglet=automatisation",
    article_id: int | None = None,
) -> None:
    """Journalise et prévient Lucas (push). `type_alerte` sert au journal et aux préférences."""
    prefixe = f"[{compte.nom}] " if compte else ""
    journaliser(
        db, compte, type_alerte, f"{titre}. {corps}".strip(". ") if corps else titre, "alerte", article_id
    )
    notifier(db, "extension", prefixe + titre, url, corps=corps)


def valider(db: Session) -> None:
    """Commit puis envoi des alertes en attente."""
    db.commit()
    envoyer_en_attente(db)


def arreter_compte(db: Session, compte: CompteVinted, raison: str) -> None:
    """Arrêt automatique : plus aucune action sur Vinted jusqu'à la reprise manuelle.
    Les tâches en attente restent en file."""
    if compte.pause:
        journaliser(db, compte, "arret", f"Déjà en pause : {raison}", "erreur")
        return
    compte.pause = True
    compte.pause_raison = raison
    alerter(
        db,
        compte,
        "arret",
        "Compte arrêté",
        f"{raison} Reprise manuelle dans Paramètres → Automatisation.",
    )
