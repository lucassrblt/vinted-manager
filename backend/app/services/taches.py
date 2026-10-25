"""File de tâches Vinted : création, priorités, budget d'actions par compte.

Toutes les actions sur Vinted passent par cette file. Le backend décide (règles, IA) et crée les
tâches ; l'extension demande la suivante, l'exécute et rend compte. Une tâche en erreur n'est jamais
relancée automatiquement.
"""

import hashlib
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import CompteVinted, TacheVinted
from app.services import horaires, reglages

# Priorité : 1 réponse acheteur, 2 offre ou relance, 3 après-vente, 4 brouillon, 5 republication ou prix.
PRIORITES = {
    "repondre_message": 1,
    "accepter_offre": 2,
    "refuser_offre": 2,
    "contre_offre": 2,
    "relance_favori": 2,
    "message_apres_vente": 3,
    "brouillon": 4,
    "republication": 5,
    "modifier_prix": 5,
    "photos_reference": 5,
}
TYPES = tuple(PRIORITES)
MODULE_PAR_TYPE = {
    "brouillon": "brouillons",
    "repondre_message": "assistant",
    "accepter_offre": "assistant",
    "refuser_offre": "assistant",
    "contre_offre": "assistant",
    "relance_favori": "favoris",
    "republication": "republication",
    "photos_reference": "republication",
    "modifier_prix": "prix",
    "message_apres_vente": "apres_vente",
}
# Réponses aux acheteurs : seules à partir la nuit, et jamais retardées par le plafond horaire.
TYPES_REPONSE_ACHETEUR = {"repondre_message", "accepter_offre", "refuser_offre", "contre_offre"}
# Ce que chaque tâche consomme dans le budget journalier (section 7.4).
CONSOMMATION: dict[str, dict[str, int]] = {
    "brouillon": {"brouillons": 1},
    "repondre_message": {"messages": 1},
    "accepter_offre": {"offres": 1},
    "refuser_offre": {"offres": 1, "messages": 1},
    "contre_offre": {"offres": 1},
    "relance_favori": {"messages": 1, "offres": 1},
    "republication": {"republications": 1},
    "modifier_prix": {},
    "message_apres_vente": {"messages": 1},
    "photos_reference": {},
}
# Téléchargement d'images publiques : n'agit pas sur le compte, hors budget.
HORS_BUDGET = {"photos_reference"}
STATUTS_COMPTES = ("en_cours", "faite", "erreur")  # une tâche commencée a agi (ou tenté d'agir) sur Vinted
# Une tâche « en cours » sans résultat après ce délai est perdue (service worker redémarré, PC éteint).
DUREE_MAX_EN_COURS = timedelta(minutes=20)
# Écart minimal entre deux actions non urgentes d'un même compte : 20 à 60 s.
ECART_MIN_S, ECART_MAX_S = 20, 60


def alea(graine: int | str, mini: float, maxi: float) -> float:
    """Tirage pseudo-aléatoire stable pour une même graine (ex. l'id d'une tâche)."""
    h = int(hashlib.sha256(str(graine).encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return mini + (maxi - mini) * h


def creer(
    db: Session,
    compte: CompteVinted,
    type_tache: str,
    payload: dict[str, Any],
    article_id: int | None = None,
    executer_apres: datetime | None = None,
    cle: str | None = None,
    statut: str = "a_faire",
) -> TacheVinted:
    """Ajoute une tâche. Avec une `cle`, une action déjà créée (même terminée) n'est jamais refaite."""
    if type_tache not in PRIORITES:
        raise ValueError(f"Type de tâche inconnu : {type_tache}")
    if cle:
        existante = db.scalar(
            select(TacheVinted).where(TacheVinted.compte_id == compte.id, TacheVinted.cle == cle).limit(1)
        )
        if existante is not None:
            return existante
    maintenant = horaires.maintenant()
    tache = TacheVinted(
        compte_id=compte.id,
        type=type_tache,
        article_id=article_id,
        payload=payload,
        priorite=PRIORITES[type_tache],
        executer_apres=executer_apres or maintenant,
        statut=statut,
        cle=cle,
        created_at=maintenant,
        tentatives=0,
    )
    db.add(tache)
    db.flush()
    return tache


def annuler(db: Session, compte: CompteVinted, type_tache: str, **filtres: Any) -> int:
    """Annule les tâches en attente d'un type (ex. une réponse remplacée par une plus récente)."""
    n = 0
    for t in db.scalars(
        select(TacheVinted).where(
            TacheVinted.compte_id == compte.id,
            TacheVinted.type == type_tache,
            TacheVinted.statut.in_(("a_faire", "a_valider")),
        )
    ):
        if all(t.payload.get(k) == v for k, v in filtres.items()):
            t.statut, t.fin_le = "annulee", horaires.maintenant()
            n += 1
    return n


# --- Budget -----------------------------------------------------------------------------------


def _commencees(db: Session, compte: CompteVinted, depuis: datetime) -> list[TacheVinted]:
    return list(
        db.scalars(
            select(TacheVinted).where(
                TacheVinted.compte_id == compte.id,
                TacheVinted.statut.in_(STATUTS_COMPTES),
                TacheVinted.debut_le >= depuis,
            )
        )
    )


def utilisation(db: Session, compte: CompteVinted) -> dict[str, int]:
    """Actions commencées aujourd'hui (heure de Paris) par catégorie, et sur la dernière heure."""
    jour = _commencees(db, compte, horaires.debut_du_jour())
    compte_par = {"brouillons": 0, "messages": 0, "offres": 0, "republications": 0}
    for t in jour:
        for categorie, n in CONSOMMATION.get(t.type, {}).items():
            compte_par[categorie] += n
    heure = [
        t
        for t in _commencees(db, compte, horaires.maintenant() - timedelta(hours=1))
        if t.type not in HORS_BUDGET
    ]
    return compte_par | {"heure": len(heure)}


def plafonds(compte: CompteVinted) -> dict[str, int]:
    r = reglages.du_compte(compte)
    b = r["budget"]
    return {
        "brouillons": int(r["brouillons"]["max_jour"]),
        "messages": int(b["messages_jour"]),
        "offres": int(b["offres_jour"]),
        "republications": int(b["republications_jour"]),
        "heure": int(b["actions_heure"]),
    }


# Part des plafonds « messages » et « offres » gardée pour les réponses aux acheteurs.
RESERVE_REPONSES = 10


def depassement(type_tache: str, usage: dict[str, int], limites: dict[str, int]) -> str | None:
    """« jour » si un plafond journalier serait dépassé, « heure » pour le plafond horaire, sinon None.
    Les actions non urgentes s'arrêtent avant les plafonds de messages et d'offres : une réserve reste
    pour répondre aux acheteurs."""
    if type_tache in HORS_BUDGET:
        return None
    reponse = type_tache in TYPES_REPONSE_ACHETEUR
    for categorie, n in CONSOMMATION.get(type_tache, {}).items():
        limite = limites[categorie]
        if not reponse and categorie in ("messages", "offres"):
            limite = max(0, limite - RESERVE_REPONSES)
        if usage[categorie] + n > limite:
            return "jour"
    if type_tache not in TYPES_REPONSE_ACHETEUR and usage["heure"] + 1 > limites["heure"]:
        return "heure"
    return None


def report(compte: CompteVinted, tache: TacheVinted, motif: str) -> datetime:
    """Nouvelle date d'une tâche reportée : heure suivante, ou lendemain à l'ouverture (étalé)."""
    if motif == "heure":
        return horaires.debut_heure_suivante() + timedelta(minutes=alea(tache.id, 0, 10))
    return horaires.ouverture_du_lendemain(compte) + timedelta(minutes=alea(tache.id, 0, 60))


def ecart_requis(tache: TacheVinted) -> timedelta:
    return timedelta(seconds=alea(f"ecart-{tache.id}", ECART_MIN_S, ECART_MAX_S))


def derniere_fin(db: Session, compte: CompteVinted) -> datetime | None:
    return db.scalar(
        select(func.max(TacheVinted.fin_le)).where(
            TacheVinted.compte_id == compte.id, TacheVinted.type.not_in(HORS_BUDGET)
        )
    )
