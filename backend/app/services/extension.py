"""Authentification de l'extension Chrome (un jeton par compte Vinted), signal de vie et surveillance."""

import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import CompteVinted, Parametres
from app.services import alertes, horaires

# Sans signal pendant ce délai : alerte « hors ligne » (une seule fois jusqu'au retour).
DELAI_HORS_LIGNE = timedelta(minutes=5)


def hasher(jeton: str) -> str:
    return hashlib.sha256(jeton.encode()).hexdigest()


def generer_jeton(compte: CompteVinted) -> str:
    """Nouveau jeton (affiché une seule fois) ; l'ancien cesse de fonctionner."""
    jeton = "vmx_" + secrets.token_urlsafe(32)
    compte.jeton_extension_hash = hasher(jeton)
    return jeton


def compte_du_jeton(db: Session, jeton: str | None) -> CompteVinted | None:
    """Comparaison en temps constant avec chaque jeton enregistré (quelques comptes seulement)."""
    if not jeton:
        return None
    empreinte = hasher(jeton)
    trouve = None
    for compte in db.scalars(select(CompteVinted).where(CompteVinted.jeton_extension_hash.is_not(None))):
        assert compte.jeton_extension_hash is not None
        if hmac.compare_digest(compte.jeton_extension_hash, empreinte):
            trouve = compte
    return trouve


def battement(
    db: Session,
    compte: CompteVinted,
    vinted_user_id: int | None,
    login: str | None,
    version: str | None,
    onglet: bool | None = None,
) -> None:
    """Signal de vie de l'extension, avec le compte Vinted connecté dans le profil Chrome."""
    maintenant = horaires.maintenant()
    compte.extension_vue_le = maintenant
    compte.extension_version = (version or "")[:40] or None
    if compte.alerte_hors_ligne_le is not None:
        compte.alerte_hors_ligne_le = None
        alertes.journaliser(db, compte, "hors_ligne", "Extension de nouveau en ligne.")
        alertes.telegram_pour(db, compte, "hors_ligne", f"[{compte.nom}] ✅ Extension de nouveau en ligne.")
    if onglet is False:
        compte.onglet_ferme_depuis = compte.onglet_ferme_depuis or maintenant
    elif onglet is True:
        if compte.alerte_onglet_le is not None:
            alertes.journaliser(db, compte, "onglet", "Onglet Vinted rouvert.")
        compte.onglet_ferme_depuis, compte.alerte_onglet_le = None, None
    if vinted_user_id is None:
        return
    nouveau = vinted_user_id != compte.vinted_user_id_vu
    compte.vinted_user_id_vu = vinted_user_id
    compte.vinted_login_vu = (login or "")[:120] or None
    if nouveau and compte.vinted_user_id is not None and vinted_user_id != compte.vinted_user_id:
        alertes.alerter(
            db,
            compte,
            "mauvais_compte",
            "Mauvais compte connecté dans ce profil",
            f"Vinted indique {login or vinted_user_id} ({vinted_user_id}), attendu {compte.vinted_user_id}. "
            "Aucune action n'est faite tant que ce n'est pas corrigé.",
        )


def surveiller(db: Session) -> None:
    """Chaque minute : extension silencieuse ou onglet Vinted fermé depuis 5 min → une alerte."""
    params = db.get(Parametres, 1)
    if params is not None and not params.automatisation_active:
        return
    maintenant = horaires.maintenant()
    for c in db.scalars(select(CompteVinted).where(CompteVinted.jeton_extension_hash.is_not(None))):
        if c.pause or c.extension_vue_le is None:
            continue
        if maintenant - c.extension_vue_le > DELAI_HORS_LIGNE and c.alerte_hors_ligne_le is None:
            c.alerte_hors_ligne_le = maintenant
            alertes.alerter(
                db,
                c,
                "hors_ligne",
                "Extension hors ligne",
                "Aucun signal depuis 5 min : PC éteint, Chrome ou le profil Chrome de ce compte fermé ?",
            )
        elif (
            c.onglet_ferme_depuis is not None
            and maintenant - c.onglet_ferme_depuis > DELAI_HORS_LIGNE
            and c.alerte_onglet_le is None
        ):
            c.alerte_onglet_le = maintenant
            alertes.alerter(
                db,
                c,
                "onglet",
                "Onglet Vinted fermé",
                "Ouvre www.vinted.fr dans le profil Chrome de ce compte.",
            )
    alertes.valider(db)
