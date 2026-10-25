"""Bot Telegram : alertes par compte Vinted, commandes (/stop, /reprendre, /etat) et boutons de l'assistant.

- TELEGRAM_BOT_TOKEN absent : rien n'est envoyé, sans erreur (les alertes restent en push et au journal).
- Pas de webhook : le backend relève les messages par `getUpdates` toutes les 5 s (fonctionne sur le PC de Lucas).
- Appairage : Paramètres → Automatisation affiche un code à 6 chiffres ; Lucas envoie `/start <code>` au bot.
- Comme les notifications push, les envois sont mis en attente sur la session et partent après le commit.
"""

import secrets
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Protocol

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.logging import log
from app.models import CompteVinted, Parametres, TacheVinted
from app.services import horaires

CLE = "telegram_en_attente"
DUREE_CODE = timedelta(minutes=30)
ATTENTE_POLLING_S = 4


class ClientTelegram(Protocol):
    def envoyer(
        self,
        chat_id: str,
        texte: str,
        boutons: list[list[dict[str, str]]] | None = None,
        silencieux: bool = False,
    ) -> None: ...

    def document(
        self, chat_id: str, nom: str, contenu: bytes, legende: str, silencieux: bool = False
    ) -> None: ...

    def repondre_bouton(self, callback_id: str, texte: str) -> None: ...

    def updates(self, offset: int, timeout: int) -> list[dict[str, Any]]: ...


class TelegramHttp:
    """Appels à l'API Bot de Telegram."""

    def __init__(self, token: str) -> None:
        self.http = httpx.Client(base_url=f"https://api.telegram.org/bot{token}/", timeout=15)

    def _appel(self, methode: str, **kwargs: Any) -> Any:
        r = self.http.post(methode, **kwargs)
        donnees = r.json()
        if not donnees.get("ok"):
            raise RuntimeError(f"Telegram {methode} : {donnees.get('description', r.status_code)}")
        return donnees["result"]

    def envoyer(
        self,
        chat_id: str,
        texte: str,
        boutons: list[list[dict[str, str]]] | None = None,
        silencieux: bool = False,
    ) -> None:
        corps: dict[str, Any] = {"chat_id": chat_id, "text": texte[:4000], "disable_notification": silencieux}
        if boutons:
            corps["reply_markup"] = {"inline_keyboard": boutons}
        self._appel("sendMessage", json=corps)

    def document(
        self, chat_id: str, nom: str, contenu: bytes, legende: str, silencieux: bool = False
    ) -> None:
        self._appel(
            "sendDocument",
            data={
                "chat_id": chat_id,
                "caption": legende[:1000],
                "disable_notification": str(silencieux).lower(),
            },
            files={"document": (nom, contenu, "application/pdf")},
        )

    def repondre_bouton(self, callback_id: str, texte: str) -> None:
        self._appel("answerCallbackQuery", json={"callback_query_id": callback_id, "text": texte[:190]})

    def updates(self, offset: int, timeout: int) -> list[dict[str, Any]]:
        r = self.http.post(
            "getUpdates", json={"offset": offset, "timeout": timeout}, timeout=timeout + 10
        ).json()
        return list(r.get("result") or []) if r.get("ok") else []


def _fabrique_defaut() -> ClientTelegram | None:
    token = get_settings().telegram_bot_token
    return TelegramHttp(token) if token else None


# Remplacée par un faux client dans les tests.
fabrique = _fabrique_defaut


def configure() -> bool:
    return bool(get_settings().telegram_bot_token)


# --- Envois en attente (après le commit) ------------------------------------------------------


@dataclass
class Envoi:
    chat_id: str
    texte: str
    boutons: list[list[dict[str, str]]] | None = None
    silencieux: bool = False
    document: tuple[str, bytes] | None = field(default=None)


def mettre_en_attente(db: Session, envoi: Envoi) -> None:
    db.info.setdefault(CLE, []).append(envoi)


def envoyer_en_attente(db: Session) -> None:
    envois: list[Envoi] = db.info.pop(CLE, [])
    if not envois:
        return
    client = fabrique()
    if client is None:
        return
    for e in envois:
        try:
            if e.document:
                client.document(e.chat_id, e.document[0], e.document[1], e.texte, e.silencieux)
            else:
                client.envoyer(e.chat_id, e.texte, e.boutons, e.silencieux)
        except Exception as exc:  # un envoi raté ne doit jamais casser le traitement
            log.warning("telegram_erreur", erreur=str(exc)[:200])


def annuler_en_attente(db: Session) -> None:
    db.info.pop(CLE, None)


def boutons_tache(tache_id: int, envoyer: bool = True, modifier: bool = True) -> list[list[dict[str, str]]]:
    """Envoyer la réponse proposée, la modifier, ou ignorer."""
    ligne = []
    if envoyer:
        ligne.append({"text": "✅ Envoyer", "callback_data": f"t:{tache_id}:envoyer"})
    if modifier:
        ligne.append({"text": "✏️ Modifier", "callback_data": f"t:{tache_id}:modifier"})
    ligne.append({"text": "🚫 Ignorer", "callback_data": f"t:{tache_id}:ignorer"})
    return [ligne]


# --- Appairage --------------------------------------------------------------------------------


def generer_code(compte: CompteVinted) -> str:
    compte.telegram_code = f"{secrets.randbelow(1_000_000):06d}"
    compte.telegram_code_expire_le = horaires.maintenant() + DUREE_CODE
    return compte.telegram_code


# --- Réception (getUpdates) -------------------------------------------------------------------


def relever(db: Session) -> int:
    """Lit les nouveaux messages du bot et les traite. Renvoie le nombre de mises à jour lues."""
    client = fabrique()
    if client is None:
        return 0
    params = db.get(Parametres, 1)
    if params is None:
        params = Parametres(id=1)
        db.add(params)
        db.flush()
    try:
        mises_a_jour = client.updates(params.telegram_offset, ATTENTE_POLLING_S)
    except Exception as exc:
        log.warning("telegram_releve_erreur", erreur=str(exc)[:200])
        return 0
    for maj in mises_a_jour:
        params.telegram_offset = max(params.telegram_offset, int(maj["update_id"]) + 1)
        try:
            traiter(db, client, params, maj)
        except Exception:
            log.exception("telegram_traitement_erreur")
            db.rollback()
            params = db.get(Parametres, 1) or params
            params.telegram_offset = max(params.telegram_offset, int(maj["update_id"]) + 1)
    db.commit()
    from app.services import alertes  # import local : alertes dépend de ce module

    alertes.envoyer_tout(db)
    return len(mises_a_jour)


def comptes_du_chat(db: Session, chat_id: str) -> list[CompteVinted]:
    return list(
        db.scalars(
            select(CompteVinted).where(CompteVinted.telegram_chat_id == chat_id).order_by(CompteVinted.id)
        )
    )


def _repondre(db: Session, chat_id: str, texte: str) -> None:
    mettre_en_attente(db, Envoi(chat_id, texte))


def traiter(db: Session, client: ClientTelegram, params: Parametres, maj: dict[str, Any]) -> None:
    if "callback_query" in maj:
        _bouton(db, client, params, maj["callback_query"])
        return
    message = maj.get("message") or {}
    texte = str(message.get("text") or "").strip()
    chat_id = str((message.get("chat") or {}).get("id") or "")
    if not chat_id or not texte:
        return
    commande, _, argument = texte.partition(" ")
    commande = commande.split("@")[0].lower()
    if commande == "/start":
        _appairer(db, chat_id, argument.strip())
        return
    comptes = comptes_du_chat(db, chat_id)
    if not comptes:
        _repondre(db, chat_id, "Ce chat n'est relié à aucun compte. Envoie /start suivi du code affiché dans "
                  "vinted-manager (Paramètres → Automatisation).")  # fmt: skip
        return
    from app.services import alertes, file_vinted  # imports locaux : dépendances circulaires

    if commande == "/stop":
        for c in comptes:
            alertes.arreter_compte(db, c, "Arrêt demandé sur Telegram (/stop).", prevenir=False)
        _repondre(db, chat_id, "⏸️ Arrêt : " + ", ".join(c.nom for c in comptes) + ". Les tâches restent en file. "
                  "/reprendre pour relancer.")  # fmt: skip
    elif commande == "/reprendre":
        for c in comptes:
            c.pause, c.pause_raison = False, None
            alertes.journaliser(db, c, "reprise", "Reprise demandée sur Telegram (/reprendre).")
        _repondre(db, chat_id, "▶️ Reprise : " + ", ".join(c.nom for c in comptes) + ".")
    elif commande == "/etat":
        _repondre(db, chat_id, "\n\n".join(file_vinted.resume_etat(db, c) for c in comptes))
    else:
        attente = (params.telegram_attente or {}).get(chat_id)
        if attente and not texte.startswith("/"):
            _remplacer_reponse(db, params, chat_id, int(attente), texte)
        else:
            _repondre(db, chat_id, "Commandes : /etat, /stop, /reprendre.")


def _appairer(db: Session, chat_id: str, code: str) -> None:
    maintenant = horaires.maintenant()
    compte = db.scalar(select(CompteVinted).where(CompteVinted.telegram_code == code)) if code else None
    if (
        compte is None
        or compte.telegram_code_expire_le is None
        or compte.telegram_code_expire_le < maintenant
    ):
        _repondre(
            db, chat_id, "Code inconnu ou expiré : génère un nouveau code dans Paramètres → Automatisation."
        )
        return
    compte.telegram_chat_id = chat_id
    compte.telegram_code, compte.telegram_code_expire_le = None, None
    from app.services import alertes

    alertes.journaliser(db, compte, "telegram", "Telegram relié à ce compte.")
    _repondre(db, chat_id, f"✅ Compte « {compte.nom} » relié. Commandes : /etat, /stop, /reprendre.")


def _tache_du_chat(db: Session, chat_id: str, tache_id: int) -> TacheVinted | None:
    tache = db.get(TacheVinted, tache_id)
    if tache is None or tache.compte_id not in {c.id for c in comptes_du_chat(db, chat_id)}:
        return None
    return tache


def _bouton(db: Session, client: ClientTelegram, params: Parametres, rappel: dict[str, Any]) -> None:
    chat_id = str(((rappel.get("message") or {}).get("chat") or {}).get("id") or "")
    morceaux = str(rappel.get("data") or "").split(":")
    reponse = "Action inconnue."
    if len(morceaux) == 3 and morceaux[0] == "t" and morceaux[1].isdigit():
        tache = _tache_du_chat(db, chat_id, int(morceaux[1]))
        if tache is None:
            reponse = "Tâche introuvable."
        elif tache.statut != "a_valider":
            reponse = "Déjà traitée."
        else:
            reponse = _decider(db, params, chat_id, tache, morceaux[2])
    try:
        client.repondre_bouton(str(rappel.get("id")), reponse)
    except Exception as exc:
        log.warning("telegram_bouton_erreur", erreur=str(exc)[:200])


def _decider(db: Session, params: Parametres, chat_id: str, tache: TacheVinted, action: str) -> str:
    from app.services import alertes, file_vinted

    compte = db.get(CompteVinted, tache.compte_id)
    assert compte is not None
    if action == "envoyer":
        if tache.type == "repondre_message" and not str(tache.payload.get("texte") or "").strip():
            return "Aucune réponse proposée : utilise Modifier."
        file_vinted.valider_tache(db, compte, tache)
        alertes.journaliser(db, compte, "validation", f"Réponse validée sur Telegram (tâche {tache.id}).")
        return "Envoi programmé."
    if action == "ignorer":
        tache.statut, tache.fin_le = "annulee", horaires.maintenant()
        alertes.journaliser(db, compte, "validation", f"Réponse ignorée sur Telegram (tâche {tache.id}).")
        return "Ignorée."
    if action == "modifier":
        params.telegram_attente = {**(params.telegram_attente or {}), chat_id: tache.id}
        _repondre(db, chat_id, "✏️ Écris la réponse à envoyer (ton prochain message sera envoyé tel quel).")
        return "J'attends ta réponse."
    return "Action inconnue."


def _remplacer_reponse(db: Session, params: Parametres, chat_id: str, tache_id: int, texte: str) -> None:
    from app.services import alertes, file_vinted

    params.telegram_attente = {k: v for k, v in (params.telegram_attente or {}).items() if k != chat_id}
    tache = _tache_du_chat(db, chat_id, tache_id)
    if tache is None or tache.statut != "a_valider":
        _repondre(db, chat_id, "Cette réponse n'est plus en attente.")
        return
    compte = db.get(CompteVinted, tache.compte_id)
    assert compte is not None
    tache.payload = {**tache.payload, "texte": texte}
    file_vinted.valider_tache(db, compte, tache)
    alertes.journaliser(db, compte, "validation", f"Réponse modifiée sur Telegram (tâche {tache.id}).")
    _repondre(db, chat_id, "✅ Réponse modifiée : envoi programmé.")
