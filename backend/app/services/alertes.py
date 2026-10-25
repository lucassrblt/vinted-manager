"""Alertes de l'automatisation Vinted : journal, notification push et Telegram (chat du compte).

Comme `notifications.notifier`, l'envoi est mis en attente sur la session et part après le commit
(`valider`) : un envoi lent ou en échec ne touche jamais la transaction.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.logging import log
from app.models import CompteVinted, JournalVinted
from app.services import horaires, reglages, telegram
from app.services.notifications import envoyer_en_attente, notifier

# Type d'entrée du journal → catégorie d'alerte réglable (Paramètres → Automatisation → Notifications).
CATEGORIES = {
    "arret": "arret",
    "mauvais_compte": "arret",
    "budget": "arret",
    "session": "session",
    "hors_ligne": "hors_ligne",
    "onglet": "hors_ligne",
    "brouillon_pret": "brouillons",
    "brouillon_erreur": "erreurs",
    "couleur": "erreurs",
    "tache_erreur": "erreurs",
    "intervention": "intervention",
    "offre_hors_regles": "offre_hors_regles",
    "vente": "vente",
    "litige": "litige",
    "recap": "recap",
}


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
        date=horaires.maintenant(),
    )
    db.add(entree)
    log.info("journal_vinted", compte=entree.compte_id, type=type_entree, niveau=niveau)
    return entree


def chats(db: Session, compte: CompteVinted | None) -> list[tuple[CompteVinted, str]]:
    """Destinataires Telegram : le chat du compte, ou ceux de tous les comptes reliés si aucun compte."""
    if compte is not None:
        return [(compte, compte.telegram_chat_id)] if compte.telegram_chat_id else []
    vus: dict[str, CompteVinted] = {}
    for c in db.scalars(select(CompteVinted).where(CompteVinted.telegram_chat_id.is_not(None))):
        assert c.telegram_chat_id
        vus.setdefault(c.telegram_chat_id, c)
    return [(c, chat) for chat, c in vus.items()]


def telegram_pour(
    db: Session,
    compte: CompteVinted | None,
    categorie: str,
    texte: str,
    boutons: list[list[dict[str, str]]] | None = None,
    document: tuple[str, bytes] | None = None,
) -> None:
    for c, chat in chats(db, compte):
        if reglages.alerte_active(c, categorie):
            # La nuit, les alertes arrivent sans son.
            silencieux = not horaires.actif(c)
            telegram.mettre_en_attente(db, telegram.Envoi(chat, texte, boutons, silencieux, document))


def alerter(
    db: Session,
    compte: CompteVinted | None,
    type_alerte: str,
    titre: str,
    corps: str = "",
    url: str = "/parametres?onglet=automatisation",
    article_id: int | None = None,
    boutons: list[list[dict[str, str]]] | None = None,
) -> None:
    """Journalise et prévient Lucas : push (type « extension ») et Telegram (chat du compte)."""
    prefixe = f"[{compte.nom}] " if compte else ""
    message = f"{titre}. {corps}".strip(". ") if corps else titre
    journaliser(db, compte, type_alerte, message, "alerte", article_id)
    notifier(db, "extension", prefixe + titre, url, corps=corps)
    texte = f"{prefixe}{titre}" + (f"\n{corps}" if corps else "")
    telegram_pour(db, compte, CATEGORIES.get(type_alerte, "erreurs"), texte, boutons)


def envoyer_tout(db: Session) -> None:
    envoyer_en_attente(db)
    telegram.envoyer_en_attente(db)


def valider(db: Session) -> None:
    """Commit puis envoi des alertes en attente (push et Telegram)."""
    db.commit()
    envoyer_tout(db)


def arreter_compte(db: Session, compte: CompteVinted, raison: str, prevenir: bool = True) -> None:
    """Arrêt : plus aucune action sur Vinted jusqu'à la reprise manuelle. Les tâches restent en file."""
    if compte.pause:
        journaliser(db, compte, "arret", f"Déjà en pause : {raison}", "erreur")
        return
    compte.pause = True
    compte.pause_raison = raison
    if not prevenir:
        journaliser(db, compte, "pause", raison)
        return
    session = "401" in raison or "session" in raison.lower()
    alerter(
        db,
        compte,
        "session" if session else "arret",
        "Session Vinted expirée" if session else "Compte arrêté",
        (
            f"{raison} Marche à suivre : ouvre www.vinted.fr dans le profil Chrome de ce compte, reconnecte-toi, "
            "puis reprends (bouton Reprendre de l'extension, /reprendre ou Paramètres → Automatisation)."
            if session
            else f"{raison} Reprise manuelle : /reprendre, bouton de l'extension ou Paramètres → Automatisation."
        ),
    )
