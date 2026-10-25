"""Brouillons Vinted automatiques : choix de l'article prêt, contrôles, charge utile pour l'extension.

L'extension crée le brouillon sur Vinted ; Lucas le relit et le publie lui-même.

Article prêt : attribué au compte, statut « reçu à publier », titre, description et prix remplis,
photos terminées, complètes (devant, dos, étiquette, 5 au total) et sans écart de couleur non validé.
"""

import io
from datetime import timedelta
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Any

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Article, CompteVinted, Parametres, PhotoArticle, TacheVinted
from app.models.enums import EtatArticle, StatutArticle
from app.services import alertes, couleur, horaires, images, photos, reglages, storage, taches
from app.services.marques import normaliser

# État vinted-manager → `condition_id` Vinted (options observées sur les catégories 1806 et 268).
CONDITION_IDS = {
    EtatArticle.NEUF_ETIQUETTE: 6,
    EtatArticle.NEUF_SANS_ETIQUETTE: 1,
    EtatArticle.TRES_BON: 2,
    EtatArticle.BON: 3,
    EtatArticle.SATISFAISANT: 4,
}
TYPES_EXIGES = ("devant", "dos", "etiquette")
NB_PHOTOS_MIN = 5
PART_PLANCHER = Decimal("0.82")
STATUTS_PHOTO_TERMINES = ("genere", "original")

# Taille du colis : 1 pour les t-shirts et hauts légers (observé, catégorie 1806), 2 sinon
# (observé pour les sweats, catégorie 268 ; hypothèse prudente pour les vestes et le reste).
MOTS_COLIS_PETIT = (
    "t-shirt", "tshirt", "tee", "top", "debardeur", "polo", "maillot", "chemise", "bonnet", "casquette",
    "chaussettes", "ceinture",
)  # fmt: skip


class BrouillonImpossible(Exception):
    """L'article ne peut pas devenir un brouillon : message affiché à Lucas."""


def arrondi_50(v: Decimal, rounding: str = ROUND_HALF_UP) -> Decimal:
    """Arrondi aux 50 centimes (au plus proche par défaut)."""
    return ((v * 2).quantize(Decimal("1"), rounding=rounding) / 2).quantize(Decimal("0.01"))


def fixer_prix_initial(article: Article, prix: Decimal | None) -> None:
    """Prix au moment de la première publication (ou de l'import) et plancher des offres (82 %)."""
    if article.prix_initial is None and prix is not None:
        article.prix_initial = prix
    if article.prix_initial is not None:
        # Arrondi vers le haut : le plancher ne descend jamais sous 82 % du prix initial.
        article.prix_plancher = arrondi_50(article.prix_initial * PART_PLANCHER, ROUND_CEILING)


def prix_texte(prix: Decimal) -> str:
    """« 24 », « 24.5 » : le format attendu par Vinted dans le champ `price`."""
    texte = f"{prix.quantize(Decimal('0.01')):f}".rstrip("0").rstrip(".")
    return texte


def package_size_id(categorie: str | None) -> int:
    texte = normaliser(categorie or "").replace(" ", "-")
    return 1 if any(m in texte for m in MOTS_COLIS_PETIT) else 2


# --- Photos publiées --------------------------------------------------------------------------


def version_publiee(photo: PhotoArticle, params: Parametres) -> str:
    """« original » ou « genere » : ce qui part réellement sur Vinted."""
    if photo.type == "devant" and params.premiere_photo_reelle:
        return "original"  # première photo réelle : l'originale redressée et recadrée
    if photo.type == "defaut" or photo.version_choisie != "genere" or not photo.fichier_genere:
        return "original"
    return "genere"


def recadrer(contenu: bytes) -> bytes:
    """Recadrage centré au format portrait 3:4 de Vinted, seulement s'il retire peu de l'image
    (25 % au plus) : on ne risque pas de couper le vêtement. Métadonnées supprimées."""
    image = Image.open(io.BytesIO(contenu))
    largeur, hauteur = image.size
    cible = 3 / 4
    ratio = largeur / hauteur
    if abs(ratio - cible) / cible <= 0.05:
        return images.preparer(contenu)
    if ratio > cible:
        nouvelle_largeur, nouvelle_hauteur = round(hauteur * cible), hauteur
    else:
        nouvelle_largeur, nouvelle_hauteur = largeur, round(largeur / cible)
    if (nouvelle_largeur * nouvelle_hauteur) / (largeur * hauteur) < 0.75:
        return images.preparer(contenu)
    gauche, haut = (largeur - nouvelle_largeur) // 2, (hauteur - nouvelle_hauteur) // 2
    sortie = io.BytesIO()
    image.convert("RGB").crop((gauche, haut, gauche + nouvelle_largeur, haut + nouvelle_hauteur)).save(
        sortie, "JPEG", quality=90, optimize=True
    )
    return sortie.getvalue()


def contenu_publie(photo: PhotoArticle, params: Parametres) -> bytes:
    if version_publiee(photo, params) == "genere":
        assert photo.fichier_genere
        return storage.chemin_absolu(photo.fichier_genere).read_bytes()
    original = storage.chemin_absolu(photo.fichier_original).read_bytes()
    return recadrer(original) if photo.type == "devant" else original


def ai_photo(liste: list[PhotoArticle], params: Parametres) -> bool:
    """Vrai dès qu'une photo publiée est une version générée (jamais faux pour la masquer)."""
    return any(version_publiee(p, params) == "genere" for p in liste)


def photos_terminees(liste: list[PhotoArticle]) -> bool:
    return bool(liste) and all(
        p.statut in STATUTS_PHOTO_TERMINES or (p.version_choisie == "original" and p.statut != "en_cours")
        for p in liste
    )


def photos_manquantes(liste: list[PhotoArticle]) -> list[str]:
    types = {p.type for p in liste}
    manquantes = [photos.TYPES[t].lower() for t in TYPES_EXIGES if t not in types]
    if len(liste) < NB_PHOTOS_MIN:
        manquantes.append(f"{NB_PHOTOS_MIN} photos au total (il y en a {len(liste)})")
    return manquantes


def photos_couleur_a_verifier(
    db: Session, liste: list[PhotoArticle], params: Parametres
) -> list[PhotoArticle]:
    """Photos publiées en version retouchée dont la couleur s'écarte trop de l'original."""
    douteuses = []
    for p in liste:
        if version_publiee(p, params) != "genere" or p.couleur_validee:
            continue
        if p.ecart_couleur is None:
            p.ecart_couleur = photos.mesurer_couleur(p)
        if p.ecart_couleur is None or p.ecart_couleur > couleur.SEUIL_DELTA_E:
            douteuses.append(p)  # non mesurable : on bloque aussi, par prudence
    return douteuses


# --- Choix du prochain brouillon --------------------------------------------------------------

# Au plus un brouillon toutes les 5 min, plus 0 à 120 s tirés au hasard.
INTERVALLE = timedelta(minutes=5)
ALEA_MAX_S = 120


def brouillons_du_jour(db: Session, compte: CompteVinted) -> int:
    """Brouillons commencés aujourd'hui (heure de Paris), réussis ou non : chaque essai agit sur Vinted."""
    return taches.utilisation(db, compte)["brouillons"]


def max_par_jour(compte: CompteVinted) -> int:
    return int(reglages.du_compte(compte)["brouillons"]["max_jour"])


def compte_pret(compte: CompteVinted) -> bool:
    """Compte non arrêté, identifiant Vinted attendu connu et identique au dernier vu par l'extension."""
    if compte.pause or compte.vinted_user_id is None:
        return False
    return compte.vinted_user_id_vu is None or compte.vinted_user_id_vu == compte.vinted_user_id


def _candidats(db: Session, compte: CompteVinted) -> list[Article]:
    avec_photos = select(PhotoArticle.article_id).distinct()
    return list(
        db.scalars(
            select(Article)
            .where(
                Article.compte_id == compte.id,
                Article.statut == StatutArticle.RECU_A_PUBLIER,
                Article.brouillon_statut.is_(None),
                Article.titre_annonce.is_not(None),
                Article.description_annonce.is_not(None),
                Article.prix_vente_cible.is_not(None),
                Article.id.in_(avec_photos),  # un article sans photo n'est pas encore préparé
            )
            .order_by(Article.updated_at, Article.id)
        )
    )


def verifier(db: Session, article: Article, params: Parametres) -> list[PhotoArticle]:
    """Lève BrouillonImpossible si l'article est incomplet. Renvoie les photos publiées, dans l'ordre."""
    liste = photos.photos_ordonnees(db, article.id)
    manquantes = photos_manquantes(liste)
    if manquantes:
        raise BrouillonImpossible("Photo manquante : " + ", ".join(manquantes) + ".")
    if article.etat not in CONDITION_IDS:
        raise BrouillonImpossible("État de l'article à compléter (neuf, très bon état…).")
    if not (article.titre_annonce or "").strip() or not (article.description_annonce or "").strip():
        raise BrouillonImpossible("Titre ou description vide.")
    if article.prix_vente_cible is None or article.prix_vente_cible <= 0:
        raise BrouillonImpossible("Prix de vente manquant.")
    return liste


def peut_demarrer(db: Session, compte: CompteVinted) -> bool:
    """Quota du jour et intervalle depuis le dernier brouillon."""
    if brouillons_du_jour(db, compte) >= max_par_jour(compte):
        return False
    dernier = db.scalar(
        select(TacheVinted)
        .where(TacheVinted.compte_id == compte.id, TacheVinted.type == "brouillon")
        .order_by(TacheVinted.created_at.desc(), TacheVinted.id.desc())
        .limit(1)
    )
    if dernier is None:
        return True
    attente = INTERVALLE + timedelta(seconds=taches.alea(f"brouillon-{dernier.id}", 0, ALEA_MAX_S))
    return horaires.maintenant() >= dernier.created_at + attente


def choisir(db: Session, compte: CompteVinted, params: Parametres) -> TacheVinted | None:
    """Crée la tâche du prochain brouillon (déjà « en cours ») pour l'article prêt le plus ancien.
    Les articles incomplets passent en erreur, avec une alerte."""
    for article in _candidats(db, compte):
        liste = photos.photos_ordonnees(db, article.id)
        if not photos_terminees(liste):
            continue  # retouche en cours : on repassera
        try:
            liste = verifier(db, article, params)
        except BrouillonImpossible as exc:
            _echec(db, compte, article, str(exc))
            continue
        douteuses = photos_couleur_a_verifier(db, liste, params)
        if douteuses:
            if not article.couleur_a_verifier:
                article.couleur_a_verifier = True
                types = ", ".join(photos.TYPES[p.type].lower() for p in douteuses)
                alertes.alerter(
                    db,
                    compte,
                    "couleur",
                    "Couleur à vérifier",
                    f"{article.nom} : {types}. Brouillon bloqué jusqu'à validation dans l'app.",
                    url=f"/stock/{article.id}",
                    article_id=article.id,
                )
            continue
        article.couleur_a_verifier = False
        article.brouillon_statut, article.brouillon_erreur = "en_cours", None
        alertes.journaliser(
            db, compte, "brouillon_debut", f"Brouillon demandé : {article.nom}", article_id=article.id
        )
        return taches.creer(
            db,
            compte,
            "brouillon",
            charge_utile(article, liste, params),
            article_id=article.id,
            statut="en_cours",
        )
    return None


def charge_utile(article: Article, liste: list[PhotoArticle], params: Parametres) -> dict[str, Any]:
    assert article.prix_vente_cible is not None and article.etat is not None
    return {
        "article_id": article.id,
        "titre": (article.titre_annonce or "").strip(),
        "description": (article.description_annonce or "").strip(),
        "prix": prix_texte(article.prix_vente_cible),
        "marque": article.marque,
        "taille": article.taille,
        "condition_id": CONDITION_IDS[EtatArticle(article.etat)],
        "couleur": article.couleur,
        "matiere": article.matiere,
        "categorie": article.categorie,
        "package_size_id": package_size_id(article.categorie),
        "ai_photo": ai_photo(liste, params),
        "photos": [{"photo_id": p.id, "type": p.type} for p in liste],
    }


# --- Résultat ---------------------------------------------------------------------------------


def _echec(db: Session, compte: CompteVinted, article: Article, message: str) -> None:
    article.brouillon_statut, article.brouillon_erreur = "erreur", message
    alertes.alerter(
        db,
        compte,
        "brouillon_erreur",
        "Brouillon refusé",
        f"{article.nom} : {message}",
        f"/stock/{article.id}",
        article.id,
    )


def enregistrer_resultat(
    db: Session,
    compte: CompteVinted,
    article: Article,
    ok: bool,
    vinted_draft_id: int | None,
    erreur: str | None,
    ai_photo_declare: bool | None,
) -> None:
    if ok:
        if vinted_draft_id is None:
            raise ValueError("vinted_draft_id manquant")
        article.brouillon_statut, article.brouillon_erreur = "cree", None
        article.vinted_draft_id = vinted_draft_id
        article.brouillon_cree_le = horaires.maintenant()
        article.ai_photo_declare = ai_photo_declare
        fixer_prix_initial(article, article.prix_vente_cible)
        alertes.journaliser(
            db, compte, "brouillon_cree", f"Brouillon créé : {article.nom}", article_id=article.id
        )
        alertes.alerter(
            db, compte, "brouillon_pret", "Brouillon prêt à publier", article.titre_annonce or article.nom,
            f"/stock/{article.id}", article.id,
        )  # fmt: skip
    else:
        _echec(db, compte, article, erreur or "Erreur inconnue de l'extension.")
