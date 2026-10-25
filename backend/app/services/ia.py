"""Appels à Claude (SDK Anthropic) : rédaction d'annonces et de réponses aux acheteurs.

- Modèle : ANTHROPIC_MODEL (défaut claude-haiku-5-5), clé : ANTHROPIC_API_KEY.
- Prompts système : fichiers texte de app/prompts/, relus à chaque appel (modifiables sans redéployer le code).
- Sortie JSON imposée par schéma (output_config.format), validée par Pydantic.
- IA_FACTICE=true : réponses déterministes sans appel réseau (démo, tests de bout en bout).
"""

import base64
import json
from pathlib import Path
from typing import Any, cast

import anthropic
from anthropic.types import MessageParam
from pydantic import BaseModel, ValidationError

from app.config import get_settings
from app.logging import log
from app.services import images

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


INTENTIONS = ["question", "offre_texte", "lot", "remerciement", "suspect", "autre"]


class ReponseAssistant(BaseModel):
    """Réponse de l'assistant à un message d'acheteur, avec sa propre évaluation du besoin d'escalade."""

    intention: str = "autre"
    reponse: str = ""
    escalade: bool = False
    raison_escalade: str = ""
    montant_propose: float | None = None


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
    "properties": {
        "intention": {"type": "string", "enum": INTENTIONS},
        "reponse": {"type": "string"},
        "escalade": {"type": "boolean"},
        "raison_escalade": {"type": "string", "description": "vide si pas d'escalade"},
        "montant_propose": {
            "anyOf": [{"type": "number"}, {"type": "null"}],
            "description": "montant en euros proposé par l'acheteur dans son message, sinon null",
        },
    },
    "required": ["intention", "reponse", "escalade", "raison_escalade", "montant_propose"],
    "additionalProperties": False,
}


def prompt_systeme(nom: str) -> str:
    texte = (DOSSIER_PROMPTS / f"{nom}.txt").read_text(encoding="utf-8").strip()
    if "{style}" in texte:  # consignes de style communes à la rédaction et à l'analyse des photos
        texte = texte.replace(
            "{style}", (DOSSIER_PROMPTS / "style_annonce.txt").read_text(encoding="utf-8").strip()
        )
    return texte


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


def _appeler(systeme: str, contenu: str | list[dict[str, Any]], schema: dict[str, Any]) -> dict[str, Any]:
    client = _client()
    try:
        reponse = client.messages.create(
            model=get_settings().anthropic_model,
            max_tokens=MAX_TOKENS,
            system=systeme,
            messages=[cast(MessageParam, {"role": "user", "content": contenu})],
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


def generer_annonce(
    fiche: dict[str, Any], modele: dict[str, str | None] | None, essai: int = 0, consigne: str | None = None
) -> AnnonceIA:
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
    if consigne:
        contenu += f"\n\nConsigne : {consigne}"
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


# --- Réécriture pour la republication ----------------------------------------------------------


class Reecriture(BaseModel):
    titre: str
    description: str


SCHEMA_REECRITURE = {
    "type": "object",
    "properties": {
        "titre": {"type": "string", "description": "60 caractères maximum"},
        "description": {"type": "string"},
    },
    "required": ["titre", "description"],
    "additionalProperties": False,
}


def reecrire_annonce(
    titre: str, description: str, fiche: dict[str, Any], mots_cles: list[str], essai: int = 0
) -> Reecriture:
    """Titre et description reformulés pour une republication (la vérification est faite par l'appelant)."""
    if get_settings().ia_factice:
        return Reecriture(titre=couper_titre(titre), description=description)
    contenu = f"Annonce actuelle :\nTitre : {titre}\nDescription :\n{description}\n\n"
    contenu += "Fiche de l'article :\n" + _fiche_texte(fiche)
    if mots_cles:
        contenu += "\n\nMots-clés à conserver : " + ", ".join(mots_cles)
    if essai:
        contenu += f"\n\nEssai n°{essai + 1} : la précédente réécriture oubliait une information obligatoire."
    try:
        r = Reecriture.model_validate(
            _appeler(prompt_systeme("reecriture_annonce"), contenu, SCHEMA_REECRITURE)
        )
    except ValidationError as exc:
        raise ErreurIA("Réponse de l'IA incomplète.") from exc
    r.titre = couper_titre(r.titre)
    r.description = r.description.strip()
    return r


# --- Analyse des photos -----------------------------------------------------------------------

TYPES_PHOTO = ["devant", "dos", "etiquette", "logo", "detail", "defaut"]
ETATS = ["neuf_avec_etiquette", "neuf_sans_etiquette", "tres_bon_etat", "bon_etat", "satisfaisant"]
TAILLE_IMAGE_IA = 1024  # px : suffisant pour lire une étiquette, peu de tokens


class AnalysePhotos(BaseModel):
    types: list[str]
    marque: str | None
    modele: str | None
    categorie: str | None
    taille: str | None
    couleur: str | None
    etat: str | None
    matiere: str | None
    defauts: str | None
    titre: str
    description: str
    mots_cles: list[str]
    prix_estime: float | None = None


def _nullable(description: str) -> dict[str, Any]:
    return {"anyOf": [{"type": "string"}, {"type": "null"}], "description": description}


SCHEMA_ANALYSE = {
    "type": "object",
    "properties": {
        "types": {"type": "array", "items": {"type": "string", "enum": TYPES_PHOTO}},
        "marque": _nullable("telle qu'écrite sur l'étiquette"),
        "modele": _nullable("modèle évident, sinon null"),
        "categorie": _nullable("type de pièce"),
        "taille": _nullable("telle qu'écrite sur l'étiquette"),
        "couleur": _nullable("couleur principale"),
        "etat": {"anyOf": [{"type": "string", "enum": ETATS}, {"type": "null"}]},
        "matiere": _nullable("composition lue sur l'étiquette"),
        "defauts": _nullable("défauts visibles"),
        "titre": {"type": "string"},
        "description": {"type": "string"},
        "mots_cles": {"type": "array", "items": {"type": "string"}},
        "prix_estime": {
            "anyOf": [{"type": "number"}, {"type": "null"}],
            "description": "prix de mise en ligne réaliste sur Vinted, en euros",
        },
    },
    "required": [
        "prix_estime",
        "types",
        "marque",
        "modele",
        "categorie",
        "taille",
        "couleur",
        "etat",
        "matiere",
        "defauts",
        "titre",
        "description",
        "mots_cles",
    ],  # fmt: skip
    "additionalProperties": False,
}


def analyser_photos(photos: list[bytes], exemples: list[str] | None = None) -> AnalysePhotos:
    """Une seule requête : type de chaque photo, fiche lue sur l'étiquette et les photos, annonce."""
    if get_settings().ia_factice:
        return _analyse_factice(len(photos))
    contenu: list[dict[str, Any]] = []
    for i, photo in enumerate(photos):
        reduite = images.preparer(photo, taille_max=TAILLE_IMAGE_IA)
        contenu.append({"type": "text", "text": f"Photo {i} :"})
        contenu.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(reduite).decode("ascii"),
                },
            }
        )
    consigne = f"{len(photos)} photos. Donne exactement {len(photos)} types, dans l'ordre."
    if exemples:
        consigne += "\nDernières ventes du vendeur (format des titres et niveau de prix) :\n" + "\n".join(
            f"- {t}" for t in exemples
        )
    contenu.append({"type": "text", "text": consigne})
    try:
        analyse = AnalysePhotos.model_validate(
            _appeler(prompt_systeme("analyse_photos"), contenu, SCHEMA_ANALYSE)
        )
    except ValidationError as exc:
        raise ErreurIA("Réponse de l'IA incomplète. Réessaie.") from exc
    analyse.types = (analyse.types + ["detail"] * len(photos))[: len(photos)]
    analyse.titre = couper_titre(analyse.titre)
    analyse.mots_cles = [m.strip().lstrip("#").lower() for m in analyse.mots_cles if m.strip()][:8]
    if analyse.prix_estime is not None and not 1 <= analyse.prix_estime <= 2000:
        analyse.prix_estime = None
    return analyse


def _analyse_factice(nb: int) -> AnalysePhotos:
    types = (["devant", "dos", "etiquette", "logo"] + ["detail"] * nb)[:nb]
    return AnalysePhotos(
        types=types,
        marque="Ralph Lauren",
        modele=None,
        categorie="Sweat demi-zip",
        taille="M",
        couleur="bleu marine",
        etat="tres_bon_etat",
        matiere=None,
        defauts=None,
        titre="Sweat demi-zip Ralph Lauren bleu marine taille M",
        description="Sweat demi-zip Ralph Lauren bleu marine, taille M.\nPorté mais en très bon état.",
        mots_cles=["ralph lauren", "sweat", "demi-zip"],
        prix_estime=40,
    )


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


def repondre_acheteur(
    messages: list[str],
    fiche: dict[str, Any] | None,
    ton: str = "",
    reponses_types: list[str] | None = None,
) -> ReponseAssistant:
    """Réponse automatique de l'assistant : intention, texte, besoin d'escalade, montant proposé."""
    if get_settings().ia_factice:
        return _assistant_factice(messages)
    contenu = "Messages de l'acheteur (du plus ancien au plus récent) :\n" + "\n".join(
        f"- {m}" for m in messages
    )
    contenu += "\n\nFiche article (seules informations fiables) :\n" + (
        _fiche_texte(fiche) if fiche else "- Article inconnu"
    )
    if ton:
        contenu += f"\n\nTon souhaité par le vendeur : {ton}"
    if reponses_types:
        contenu += "\n\nRéponses types du vendeur :\n" + "\n".join(f"- {r}" for r in reponses_types)
    contenu += "\n\nMode automatique : la réponse partira sans relecture si escalade = false."
    try:
        r = ReponseAssistant.model_validate(
            _appeler(prompt_systeme("reponse_message"), contenu, SCHEMA_REPONSE)
        )
    except ValidationError as exc:
        raise ErreurIA("Réponse de l'IA incomplète.") from exc
    r.reponse = r.reponse.strip()
    if r.intention not in INTENTIONS:
        r.intention = "autre"
    return r


def _assistant_factice(messages: list[str]) -> ReponseAssistant:
    texte = " ".join(messages).lower()
    if "remerci" in texte or texte.startswith("merci"):
        return ReponseAssistant(intention="remerciement", reponse="Avec plaisir, bonne journée !")
    return ReponseAssistant(
        intention="question",
        reponse="Bonjour, oui il est toujours disponible ! N'hésite pas si tu as une question.",
    )


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
