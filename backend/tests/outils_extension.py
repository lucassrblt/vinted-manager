"""Fabriques communes aux tests de l'extension : comptes, jetons, articles prêts avec photos."""

import io
from datetime import datetime
from decimal import Decimal as D

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app.models import Article, CompteVinted, PhotoArticle
from app.models.enums import StatutArticle
from app.services import extension, horaires, storage
from app.services.stats import tz

LUCAS_VINTED = 3201823662
SOEUR_VINTED = 3209999999


def jpeg(largeur: int = 600, hauteur: int = 800, couleur: str | tuple[int, int, int] = "gray") -> bytes:
    tampon = io.BytesIO()
    Image.new("RGB", (largeur, hauteur), couleur).save(tampon, "JPEG")
    return tampon.getvalue()


def creer_compte(db: Session, nom: str, vinted_user_id: int | None) -> tuple[CompteVinted, str]:
    compte = CompteVinted(nom=nom, vinted_user_id=vinted_user_id)
    db.add(compte)
    db.flush()
    jeton = extension.generer_jeton(compte)
    db.commit()
    return compte, jeton


def entetes(jeton: str) -> dict[str, str]:
    return {"X-Extension-Token": jeton}


def article_pret(
    db: Session,
    compte: CompteVinted | None,
    nom: str = "T-shirt Nike ACG violet",
    types: tuple[str, ...] = ("devant", "dos", "etiquette", "logo", "detail"),
    couleur_retouche: str | tuple[int, int, int] = (120, 100, 180),
    categorie: str = "T-shirt",
) -> Article:
    """Article complet : fiche, annonce, prix et photos retouchées (sauf défauts)."""
    a = Article(
        nom=nom,
        marque="Nike ACG",
        categorie=categorie,
        taille="M",
        couleur="violet",
        matiere="100% coton",
        etat="neuf_avec_etiquette",
        prix_achat_net=D("5"),
        prix_vente_cible=D("24"),
        statut=StatutArticle.RECU_A_PUBLIER,
        compte_id=compte.id if compte else None,
        titre_annonce=f"{nom} taille M",
        description_annonce="T-shirt Nike ACG violet, taille M, super sympa.\nPorté mais en très bon état.",
    )
    db.add(a)
    db.flush()
    for i, t in enumerate(types):
        original = storage.ecrire_fichier(
            f"photos/article-{a.id}", f"{t}.jpg", jpeg(600, 800, (120, 100, 180))
        )
        p = PhotoArticle(article_id=a.id, type=t, ordre=i, fichier_original=original)
        if t == "defaut":
            p.statut, p.version_choisie = "original", "original"
        else:
            p.fichier_genere = storage.ecrire_fichier(
                f"photos/article-{a.id}", f"{t}-ia.jpg", jpeg(600, 800, couleur_retouche)
            )
            p.statut, p.version_choisie = "genere", "genere"
        db.add(p)
    db.commit()
    return a


def a_heure(monkeypatch: pytest.MonkeyPatch, heure: int, minute: int = 0) -> datetime:
    """Fige l'heure vue par les règles d'horaires (Europe/Paris), aujourd'hui."""
    maintenant = datetime.now(tz()).replace(hour=heure, minute=minute, second=0, microsecond=0)
    monkeypatch.setattr(horaires, "utcnow", lambda: maintenant)
    return maintenant


def heartbeat(client: TestClient, jeton: str, vinted_user_id: int, login: str = "moi") -> None:
    r = client.post(
        "/api/extension/heartbeat",
        json={"vinted_user_id": vinted_user_id, "login": login, "version": "0.1.0"},
        headers=entetes(jeton),
    )
    assert r.status_code == 200, r.text
