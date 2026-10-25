"""Réglages de l'automatisation Vinted, par compte (JSON sur CompteVinted).

Les valeurs par défaut sont celles de la spécification ; ce qui est enregistré sur le compte les
remplace clé par clé (fusion récursive), si bien qu'un nouveau réglage prend sa valeur par défaut
sur les comptes existants.
"""

import copy
from typing import Any

from app.models import CompteVinted

MODULES = ("brouillons", "assistant", "favoris", "republication", "prix", "apres_vente")

MESSAGE_FAVORI_DEFAUT = "Hello, merci pour ton favori ! Je te propose une petite réduction si ça te tente."
MESSAGE_APRES_VENTE_DEFAUT = (
    "Merci beaucoup pour ton achat ! Je prépare le colis et je l'envoie au plus vite. Bonne journée !"
)
TYPES_ALERTES = {
    "vente": "Vente",
    "intervention": "Intervention requise (assistant)",
    "offre_hors_regles": "Offre hors règles",
    "session": "Session Vinted expirée",
    "hors_ligne": "Onglet ou PC hors ligne",
    "arret": "Arrêt automatique",
    "litige": "Litige ou retour",
    "brouillons": "Brouillons prêts",
    "recap": "Récapitulatif quotidien",
    "erreurs": "Erreurs des tâches",
}

DEFAUTS: dict[str, Any] = {
    # Modules : chacun peut être coupé pour ce compte (l'interrupteur global est dans Parametres).
    "modules": {m: True for m in MODULES},
    # Heures actives (Europe/Paris) : la nuit, seules les réponses aux acheteurs partent.
    "heures": {"debut": 8, "fin": 23},
    "brouillons": {"max_jour": 6},
    # Budget d'actions partagé par tous les modules (section 7.4).
    "budget": {"republications_jour": 40, "offres_jour": 60, "messages_jour": 120, "actions_heure": 15},
    "republication": {
        "cadence_jours": 5,
        "conversation_active_minutes": 60,
        "rotation_min": 1.5,
        "rotation_max": 2.5,
        "zoom_min": 4.5,
        "zoom_max": 5.5,
        "luminosite_min": 2.0,
        "luminosite_max": 5.0,
        "qualite_min": 85,
        "qualite_max": 92,
    },
    "prix": {
        "baisse_pct": 5,
        "delai_min_heures": 48,
        "delai_max_heures": 72,
        "plancher_pct": 82,
        "arrondi": 0.5,
    },
    "favoris": {
        "messages": [MESSAGE_FAVORI_DEFAUT],
        "reduction_pct": 10,
        "delai_min_s": 20,
        "delai_max_s": 60,
    },
    "assistant": {"seuil_acceptation_pct": 90, "seuil_refus_pct": 50, "ton": "", "reponses_types": []},
    "apres_vente": {"messages": [MESSAGE_APRES_VENTE_DEFAUT], "heure_recap": "17:30"},
    "notifications": {"types": dict.fromkeys(TYPES_ALERTES, True)},
}


def _fusionner(base: dict[str, Any], ajout: dict[str, Any]) -> dict[str, Any]:
    resultat = copy.deepcopy(base)
    for cle, valeur in ajout.items():
        if isinstance(valeur, dict) and isinstance(resultat.get(cle), dict):
            resultat[cle] = _fusionner(resultat[cle], valeur)
        else:
            resultat[cle] = copy.deepcopy(valeur)
    return resultat


def du_compte(compte: CompteVinted) -> dict[str, Any]:
    return _fusionner(DEFAUTS, compte.reglages or {})


def enregistrer(compte: CompteVinted, modifications: dict[str, Any]) -> dict[str, Any]:
    """Applique des modifications partielles (validées) et renvoie les réglages complets."""
    inconnues = [c for c in modifications if c not in DEFAUTS]
    if inconnues:
        raise ReglageInvalide(f"Réglage inconnu : {', '.join(inconnues)}.")
    nouveaux = _fusionner(compte.reglages or {}, modifications)
    valider(_fusionner(DEFAUTS, nouveaux))
    compte.reglages = nouveaux
    return du_compte(compte)


def module_actif(compte: CompteVinted, module: str) -> bool:
    return bool(du_compte(compte)["modules"].get(module, False))


def alerte_active(compte: CompteVinted | None, type_alerte: str) -> bool:
    if compte is None:
        return True
    return bool(du_compte(compte)["notifications"]["types"].get(type_alerte, True))


class ReglageInvalide(ValueError):
    pass


def valider(r: dict[str, Any]) -> None:
    """Contrôle les bornes des réglages complets (après fusion). Lève ReglageInvalide."""

    def entre(chemin: str, mini: float, maxi: float) -> None:
        section, cle = chemin.split(".")
        v = r[section][cle]
        if not isinstance(v, int | float) or isinstance(v, bool) or not mini <= v <= maxi:
            raise ReglageInvalide(f"{chemin} : valeur attendue entre {mini} et {maxi}.")

    entre("heures.debut", 0, 23)
    entre("heures.fin", 1, 24)
    if r["heures"]["debut"] >= r["heures"]["fin"]:
        raise ReglageInvalide("Heures actives : le début doit précéder la fin.")
    entre("brouillons.max_jour", 0, 20)
    for cle, maxi in (
        ("republications_jour", 100),
        ("offres_jour", 200),
        ("messages_jour", 300),
        ("actions_heure", 60),
    ):
        entre(f"budget.{cle}", 0, maxi)
    entre("republication.cadence_jours", 1, 60)
    entre("republication.conversation_active_minutes", 0, 24 * 60)
    entre("prix.baisse_pct", 0, 30)
    entre("prix.plancher_pct", 50, 100)
    entre("prix.delai_min_heures", 1, 24 * 30)
    entre("prix.delai_max_heures", r["prix"]["delai_min_heures"], 24 * 30)
    entre("favoris.reduction_pct", 0, 50)
    entre("favoris.delai_min_s", 5, 3600)
    entre("favoris.delai_max_s", r["favoris"]["delai_min_s"], 3600)
    entre("assistant.seuil_acceptation_pct", 50, 100)
    entre("assistant.seuil_refus_pct", 0, r["assistant"]["seuil_acceptation_pct"])
    for section in ("favoris", "apres_vente"):
        messages = r[section]["messages"]
        if not isinstance(messages, list) or not all(isinstance(m, str) and m.strip() for m in messages):
            raise ReglageInvalide(f"{section}.messages : liste de textes non vides attendue.")
    heure = str(r["apres_vente"]["heure_recap"])
    h, _, m = heure.partition(":")
    if not (h.isdigit() and m.isdigit() and 0 <= int(h) <= 23 and 0 <= int(m) <= 59):
        raise ReglageInvalide("apres_vente.heure_recap : format HH:MM attendu.")
