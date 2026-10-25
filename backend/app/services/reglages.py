"""Réglages de l'automatisation Vinted, par compte (JSON sur CompteVinted).

Les valeurs par défaut sont celles de la spécification ; ce qui est enregistré sur le compte les
remplace clé par clé (fusion récursive), si bien qu'un nouveau réglage prend sa valeur par défaut
sur les comptes existants.
"""

import copy
from typing import Any

from app.models import CompteVinted

MODULES = ("brouillons", "assistant", "favoris", "republication", "prix", "apres_vente")

DEFAUTS: dict[str, Any] = {
    # Modules : chacun peut être coupé pour ce compte (l'interrupteur global est dans Parametres).
    "modules": {m: True for m in MODULES},
    "heures": {"debut": 8, "fin": 23},
    "brouillons": {"max_jour": 6},
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
    """Applique des modifications partielles et renvoie les réglages complets."""
    compte.reglages = _fusionner(compte.reglages or {}, modifications)
    return du_compte(compte)


def module_actif(compte: CompteVinted, module: str) -> bool:
    return bool(du_compte(compte)["modules"].get(module, False))
