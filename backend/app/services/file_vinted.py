"""Distribution des tâches à l'extension et traitement de leurs résultats.

`suivante` : la tâche la plus prioritaire dont l'heure est venue, si le compte peut agir (interrupteur
global, pause, compte Vinted attendu), dans les heures actives (sauf réponses aux acheteurs) et dans le
budget d'actions. Faute de tâche, un brouillon peut être lancé.
"""

from collections.abc import Callable
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Article, CompteVinted, Parametres, TacheVinted
from app.services import alertes, brouillons, horaires, reglages, taches

Rappel = Callable[[Session, CompteVinted, TacheVinted, bool], None]
# Traitement du résultat selon le type de tâche (complété par les modules des phases suivantes).
APRES: dict[str, Rappel] = {}
# Événements remontés par l'extension : type → traitement, qui renvoie la réponse à l'extension.
EVENEMENTS: dict[str, Callable[[Session, CompteVinted, dict[str, Any]], dict[str, Any]]] = {}


def apres(type_tache: str) -> Callable[[Rappel], Rappel]:
    def enregistrer(f: Rappel) -> Rappel:
        APRES[type_tache] = f
        return f

    return enregistrer


def compte_disponible(compte: CompteVinted, params: Parametres) -> bool:
    return params.automatisation_active and brouillons.compte_pret(compte)


def _interrompre_perimees(db: Session, compte: CompteVinted) -> bool:
    """Passe en erreur les tâches restées « en cours » trop longtemps (jamais relancées).
    Renvoie True s'il reste une tâche en cours : une seule à la fois par compte."""
    reste = False
    limite = horaires.maintenant() - taches.DUREE_MAX_EN_COURS
    for t in db.scalars(
        select(TacheVinted).where(TacheVinted.compte_id == compte.id, TacheVinted.statut == "en_cours")
    ):
        if t.debut_le is not None and t.debut_le < limite:
            terminer(
                db,
                compte,
                t,
                ok=False,
                erreur="Tâche interrompue (aucun résultat de l'extension) : vérifie sur Vinted avant de relancer.",
            )
        else:
            reste = True
    return reste


def demarrer(tache: TacheVinted) -> TacheVinted:
    tache.statut, tache.debut_le = "en_cours", horaires.maintenant()
    tache.tentatives += 1
    return tache


def suivante(
    db: Session, compte: CompteVinted, params: Parametres, types: set[str] | None = None
) -> TacheVinted | None:
    """Tâche à exécuter maintenant (passée « en cours »), ou None. Commit et alertes inclus."""
    tache = _suivante(db, compte, params, types)
    alertes.valider(db)
    return tache


def _suivante(
    db: Session, compte: CompteVinted, params: Parametres, types: set[str] | None
) -> TacheVinted | None:
    if not compte_disponible(compte, params) or _interrompre_perimees(db, compte):
        return None
    maintenant = horaires.maintenant()
    actif = horaires.actif(compte)
    usage, limites = taches.utilisation(db, compte), taches.plafonds(compte)
    derniere = taches.derniere_fin(db, compte)
    requete = (
        select(TacheVinted)
        .where(
            TacheVinted.compte_id == compte.id,
            TacheVinted.statut == "a_faire",
            TacheVinted.executer_apres <= maintenant,
        )
        .order_by(TacheVinted.priorite, TacheVinted.executer_apres, TacheVinted.id)
    )
    if types is not None:
        requete = requete.where(TacheVinted.type.in_(types))
    for t in db.scalars(requete):
        if not reglages.module_actif(compte, taches.MODULE_PAR_TYPE[t.type]):
            continue  # module coupé : la tâche attend en file
        reponse = t.type in taches.TYPES_REPONSE_ACHETEUR
        if not actif and not reponse:
            continue  # la nuit, seules les réponses aux acheteurs partent
        motif = taches.depassement(t.type, usage, limites)
        if motif is not None:
            if reponse:
                # Plus de 120 messages ou 60 offres dans la journée : anormal, on arrête tout.
                alertes.arreter_compte(
                    db, compte, f"Budget journalier atteint ({t.type}) : arrêt par sécurité."
                )
                return None
            t.executer_apres = taches.report(compte, t, motif)
            alertes.journaliser(
                db,
                compte,
                "budget",
                f"Tâche {t.id} ({t.type}) reportée au {horaires.local(t.executer_apres):%d/%m %H:%M} (budget {motif}).",
                article_id=t.article_id,
            )
            continue
        if not reponse and derniere is not None and maintenant - derniere < taches.ecart_requis(t):
            continue  # pas deux actions à la suite : on laisse passer quelques dizaines de secondes
        return demarrer(t)
    if types is not None and "brouillon" not in types:
        return None
    return _brouillon(db, compte, params, usage, limites, derniere)


def _brouillon(
    db: Session,
    compte: CompteVinted,
    params: Parametres,
    usage: dict[str, int],
    limites: dict[str, int],
    derniere: Any,
) -> TacheVinted | None:
    if not reglages.module_actif(compte, "brouillons") or not horaires.actif(compte):
        return None
    if taches.depassement("brouillon", usage, limites) or not brouillons.peut_demarrer(db, compte):
        return None
    if derniere is not None and horaires.maintenant() - derniere < taches.ecart_requis(TacheVinted(id=0)):
        return None
    tache = brouillons.choisir(db, compte, params)
    if tache is not None:
        tache.debut_le, tache.tentatives = horaires.maintenant(), 1
    return tache


# --- Résultats ---------------------------------------------------------------------------------


def terminer(
    db: Session,
    compte: CompteVinted,
    tache: TacheVinted,
    ok: bool,
    resultat: dict[str, Any] | None = None,
    erreur: str | None = None,
    arret: bool = False,
    erreur_vinted: bool = False,
) -> None:
    tache.statut = "faite" if ok else "erreur"
    tache.resultat, tache.erreur = resultat, None if ok else (erreur or "Erreur inconnue de l'extension.")
    tache.erreur_vinted = bool(not ok and (erreur_vinted or arret))
    tache.fin_le = horaires.maintenant()
    rappel = APRES.get(tache.type)
    if rappel is not None:
        rappel(db, compte, tache, ok)
    elif not ok and not tache.payload.get("erreur_silencieuse"):
        alertes.alerter(
            db,
            compte,
            "tache_erreur",
            f"Échec : {tache.type.replace('_', ' ')}",
            tache.erreur or "",
            article_id=tache.article_id,
        )
    if arret:
        alertes.arreter_compte(db, compte, tache.erreur or "Réponse inattendue de Vinted.")
    elif tache.erreur_vinted and _erreurs_consecutives(db, compte) >= 3:
        alertes.arreter_compte(db, compte, "3 erreurs Vinted consécutives : arrêt par sécurité.")


def _erreurs_consecutives(db: Session, compte: CompteVinted) -> int:
    dernieres = db.scalars(
        select(TacheVinted)
        .where(TacheVinted.compte_id == compte.id, TacheVinted.statut.in_(("faite", "erreur")))
        .order_by(TacheVinted.fin_le.desc(), TacheVinted.id.desc())
        .limit(10)
    ).all()
    n = 0
    for t in dernieres:
        if t.statut == "faite":
            break
        if (
            t.erreur_vinted
        ):  # un refus d'un contrôle de l'extension ne compte pas (et n'interrompt pas la série)
            n += 1
    return n


def valider_tache(db: Session, compte: CompteVinted, tache: TacheVinted) -> None:
    """Lucas valide une action proposée (Telegram ou app) : elle part avec le délai habituel."""
    tache.statut = "a_faire"
    tache.executer_apres = horaires.maintenant() + horaires.delai_reponse(compte)


@apres("brouillon")
def _apres_brouillon(db: Session, compte: CompteVinted, tache: TacheVinted, ok: bool) -> None:
    article = db.get(Article, tache.article_id) if tache.article_id else None
    if article is None:
        return
    r = tache.resultat or {}
    brouillons.enregistrer_resultat(
        db, compte, article, ok, r.get("vinted_draft_id"), tache.erreur, r.get("ai_photo")
    )


# --- État (Telegram /etat, app) ---------------------------------------------------------------


def en_file(db: Session, compte: CompteVinted) -> dict[str, int]:
    lignes = db.execute(
        select(TacheVinted.statut, func.count(TacheVinted.id))
        .where(
            TacheVinted.compte_id == compte.id, TacheVinted.statut.in_(("a_faire", "a_valider", "en_cours"))
        )
        .group_by(TacheVinted.statut)
    ).all()
    return {str(statut): int(n) for statut, n in lignes}


def resume_etat(db: Session, compte: CompteVinted) -> str:
    params = db.get(Parametres, 1)
    usage, limites = taches.utilisation(db, compte), taches.plafonds(compte)
    file = en_file(db, compte)
    if params is not None and not params.automatisation_active:
        etat = "⏹️ automatisation coupée (interrupteur global)"
    elif compte.pause:
        etat = f"⏸️ en pause : {compte.pause_raison or '—'}"
    else:
        etat = "▶️ actif"
    vu = (
        horaires.local(compte.extension_vue_le).strftime("%d/%m %H:%M")
        if compte.extension_vue_le
        else "jamais"
    )
    return (
        f"{compte.nom} : {etat}\n"
        f"Extension vue : {vu}\n"
        f"File : {file.get('a_faire', 0)} à faire, {file.get('a_valider', 0)} à valider, {file.get('en_cours', 0)} en cours\n"
        f"Aujourd'hui : {usage['brouillons']}/{limites['brouillons']} brouillons, {usage['messages']}/{limites['messages']} "
        f"messages, {usage['offres']}/{limites['offres']} offres, {usage['republications']}/{limites['republications']} "
        f"republications ; {usage['heure']}/{limites['heure']} actions sur la dernière heure"
    )
