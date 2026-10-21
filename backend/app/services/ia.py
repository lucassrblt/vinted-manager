"""Appels à Claude (SDK Anthropic) : rédaction d'annonces et de réponses aux acheteurs.

- Modèle : ANTHROPIC_MODEL (défaut claude-haiku-5-5), clé : ANTHROPIC_API_KEY.
- Prompts système : fichiers texte de app/prompts/, relus à chaque appel (modifiables sans redéployer le code).
- Sortie JSON imposée par schéma (output_config.format), validée par Pydantic.
- IA_FACTICE=true : réponses déterministes sans appel réseau (démo, tests de bout en bout).
"""

import json
from pathlib import Path
from typing import Any

import anthropic
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.logging import log

DOSSIER_PROMPTS = Path(__file__).resolve().parent.parent / "prompts"
TITRE_MAX = 60
MAX_TOKENS = 8000


class ErreurIA(Exception):
    """Erreur affichable telle quelle à l'utilisateur."""


class AnnonceIA(BaseModel):
    titre: str
    description: str
    mots_cles: list[str]


class ReponseIA(BaseModel):
    reponse: str


SCHEMA_ANNONCE = {
    "type": "object",
    "properties": {
        "titre": {"type": "string", "description": "60 caractères maximum"},
        "description": {"type": "string"},
        "mots_cles": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["titre", "description", "mots_cles"],
    "additionalProperties": False,
}
SCHEMA_REPONSE = {
    "type": "object",
    "properties": {"reponse": {"type": "string"}},
    "required": ["reponse"],
    "additionalProperties": False,
}


def prompt_systeme(nom: str) -> str:
    return (DOSSIER_PROMPTS / f"{nom}.txt").read_text(encoding="utf-8").strip()


def _client() -> anthropic.Anthropic:
    cle = get_settings().anthropic_api_key
    if not cle:
        raise ErreurIA(
            "L'IA n'est pas configurée : la variable ANTHROPIC_API_KEY n'est pas définie sur le serveur."
        )
    return anthropic.Anthropic(api_key=cle, max_retries=2, timeout=60)


def _message_erreur(exc: anthropic.APIError) -> str:
    texte = str(getattr(exc, "message", "") or exc).lower()
    if isinstance(exc, anthropic.AuthenticationError):
        return "Clé API Anthropic refusée : vérifie ANTHROPIC_API_KEY."
    if isinstance(exc, anthropic.PermissionDeniedError):
        return "Cette clé API n'a pas accès au modèle demandé."
    if isinstance(exc, anthropic.NotFoundError):
        return f"Modèle introuvable : vérifie ANTHROPIC_MODEL (actuellement « {get_settings().anthropic_model} »)."
    if isinstance(exc, anthropic.RateLimitError):
        attente = exc.response.headers.get("retry-after") if exc.response is not None else None
        return "Trop de demandes à l'IA en ce moment (limite de débit atteinte). " + (
            f"Réessaie dans {attente} s." if attente else "Réessaie dans une minute."
        )
    if isinstance(exc, anthropic.BadRequestError) and ("credit" in texte or "billing" in texte):
        return "Crédit API Anthropic épuisé : recharge ton compte sur console.anthropic.com (Billing)."
    if isinstance(exc, anthropic.APITimeoutError):
        return "L'IA a mis trop de temps à répondre. Réessaie."
    if isinstance(exc, anthropic.APIConnectionError):
        return "Impossible de joindre l'API Anthropic depuis le serveur. Réessaie dans un instant."
    if isinstance(exc, anthropic.APIStatusError) and exc.status_code >= 500:
        return "Le service d'IA est momentanément indisponible ou surchargé. Réessaie dans un instant."
    return "La demande à l'IA a échoué. Réessaie, et si le problème continue, vérifie la configuration."


def _appeler(systeme: str, contenu: str, schema: dict[str, Any]) -> dict[str, Any]:
    client = _client()
    try:
        reponse = client.messages.create(
            model=get_settings().anthropic_model,
            max_tokens=MAX_TOKENS,
            system=systeme,
            messages=[{"role": "user", "content": contenu}],
            # Tâche de rédaction courte : effort bas, sortie JSON imposée par le schéma.
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        )
    except anthropic.APIError as exc:
        log.warning("ia_erreur", type=type(exc).__name__)
        raise ErreurIA(_message_erreur(exc)) from exc
    if reponse.stop_reason == "refusal":
        raise ErreurIA("L'IA a refusé de rédiger ce texte. Reformule la fiche et réessaie.")
    if reponse.stop_reason == "max_tokens":
        raise ErreurIA("La réponse de l'IA a été coupée. Réessaie.")
    texte = next((b.text for b in reponse.content if b.type == "text"), None)
    if not texte:
        raise ErreurIA("L'IA n'a renvoyé aucun texte. Réessaie.")
    log.info("ia_ok", entree=reponse.usage.input_tokens, sortie=reponse.usage.output_tokens)
    try:
        return dict(json.loads(texte))
    except json.JSONDecodeError as exc:
        raise ErreurIA("Réponse de l'IA illisible. Réessaie.") from exc


def couper_titre(titre: str) -> str:
    titre = " ".join(titre.split())
    if len(titre) <= TITRE_MAX:
        return titre
    coupe = titre[:TITRE_MAX].rsplit(" ", 1)[0]
    return coupe or titre[:TITRE_MAX]


# --- Annonces ---------------------------------------------------------------------------------


def _fiche_texte(fiche: dict[str, Any]) -> str:
    libelles = {
        "marque": "Marque", "modele": "Modèle", "categorie": "Catégorie", "taille": "Taille", "couleur": "Couleur",
        "etat": "État", "matiere": "Matière", "defauts": "Défauts", "mesures": "Mesures", "nom": "Nom interne",
    }  # fmt: skip
    lignes = []
    for cle, libelle in libelles.items():
        valeur = fiche.get(cle)
        if isinstance(valeur, dict):
            valeur = ", ".join(f"{k} : {v}" for k, v in valeur.items() if v not in (None, ""))
        if valeur:
            lignes.append(f"- {libelle} : {valeur}")
    return "\n".join(lignes)


def generer_annonce(fiche: dict[str, Any], modele: dict[str, str | None] | None, essai: int = 0) -> AnnonceIA:
    if get_settings().ia_factice:
        return _annonce_factice(fiche)
    contenu = "Fiche de l'article (seules informations fiables) :\n" + _fiche_texte(fiche)
    if modele:
        contenu += "\n\nModèle d'annonce pour cette catégorie :"
        for cle, libelle in (
            ("structure_titre", "Titre"),
            ("structure_description", "Description"),
            ("mots_cles", "Mots-clés"),
        ):
            if modele.get(cle):
                contenu += f"\n- {libelle} : {modele[cle]}"
    if essai:
        contenu += f"\n\nProposition n°{essai + 1} : formule-la différemment des précédentes."
    try:
        annonce = AnnonceIA.model_validate(
            _appeler(prompt_systeme("annonce_systeme"), contenu, SCHEMA_ANNONCE)
        )
    except ValidationError as exc:
        raise ErreurIA("Réponse de l'IA incomplète. Réessaie.") from exc
    annonce.titre = couper_titre(annonce.titre)
    annonce.mots_cles = [m.strip().lstrip("#").lower() for m in annonce.mots_cles if m.strip()][:10]
    return annonce


def _annonce_factice(fiche: dict[str, Any]) -> AnnonceIA:
    morceaux = [fiche.get(c) for c in ("categorie", "marque", "couleur", "taille")]
    titre = couper_titre(" ".join(str(m) for m in morceaux if m) or str(fiche.get("nom") or "Article"))
    etat = fiche.get("etat") or "bon état"
    description = f"{titre}, en {str(etat).lower()}."
    if fiche.get("defauts"):
        description += f" À noter : {fiche['defauts']}."
    description += " N'hésite pas si tu as une question. Possibilité de faire un lot."
    mots = [str(m).lower() for m in morceaux if m]
    return AnnonceIA(titre=titre, description=description, mots_cles=mots)


# --- Réponses aux messages et aux offres ------------------------------------------------------


def suggerer_reponse(
    message: str,
    type_message: str,
    fiche: dict[str, Any] | None,
    decision: dict[str, Any] | None,
    modeles: list[dict[str, str]],
) -> str:
    if get_settings().ia_factice:
        return _reponse_factice(type_message, decision)
    contenu = f"Message de l'acheteur ({'offre' if type_message == 'offre' else 'message'}) :\n{message}\n"
    contenu += "\nFiche article :\n" + (_fiche_texte(fiche) if fiche else "- Article inconnu")
    if decision:
        contenu += f"\n\nDécision à appliquer : {decision['decision']}"
        if decision.get("montant_propose"):
            contenu += f" (contre-proposition : {decision['montant_propose']} €)"
        contenu += f"\nMontant de l'offre : {decision['montant_offre']} €"
    if modeles:
        contenu += "\n\nModèles de réponse disponibles :\n" + "\n".join(
            f"- {m['contexte']} : {m['texte']}" for m in modeles
        )
    try:
        return ReponseIA.model_validate(
            _appeler(prompt_systeme("reponse_message"), contenu, SCHEMA_REPONSE)
        ).reponse.strip()
    except ValidationError as exc:
        raise ErreurIA("Réponse de l'IA incomplète. Réessaie.") from exc


def _reponse_factice(type_message: str, decision: dict[str, Any] | None) -> str:
    if type_message != "offre" or not decision:
        return "Bonjour, merci pour ton message ! Je regarde et je reviens vers toi rapidement."
    if decision["decision"] == "accepter":
        return "Bonjour, merci pour ton offre, je l'accepte avec plaisir !"
    if decision["decision"] == "contre_proposer":
        return f"Bonjour, merci pour ton offre ! Je peux te le proposer à {decision['montant_propose']} €, ça te va ?"
    return (
        "Bonjour, merci pour ton offre, mais je ne peux pas descendre autant sur cet article. Belle journée !"
    )
