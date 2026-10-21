"""Données de démonstration (base vide uniquement) : batches, articles, ventes, envois, messages."""

import random
from datetime import timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import Article, Batch, Envoi, HistoriqueStatut, Message, Vente
from app.models.enums import StatutArticle, StatutEnvoi
from app.seed.modeles import installer_modeles
from app.seed.regles import installer_regles
from app.services import marques
from app.services.remise import repartir_remise

PRODUITS = [
    ("Pull demi-zip polaire Ralph Lauren", "17.64", "45"),
    ("Hoodie Carhartt WIP", "20.25", "38"),
    ("T-shirt Comme des Garçons Play cœur", "7.85", "24"),
    ("Polaire Patagonia Better Sweater", "21.45", "50"),
    ("Bonnet Ralph Lauren", "4.98", "16"),
    ("Veste Dickies Eisenhower", "19.90", "40"),
    ("Pull Lacoste demi-zip", "18.50", "40"),
    ("Casquette Ralph Lauren", "6.13", "18"),
]
COULEURS = ["Noir", "Gris clair", "Bleu marine", "Blanc", "Kaki"]
TAILLES = ["S", "M", "L", "XL"]


def installer_demo(db: Session) -> dict[str, int]:
    if db.scalar(select(func.count(Article.id))):
        raise ValueError("La base contient déjà des articles : la démo ne s'installe que sur une base vide.")
    installer_regles(db)
    installer_modeles(db)
    rng = random.Random(42)
    maintenant = utcnow()
    nb = {"batches": 0, "articles": 0, "ventes": 0}
    for i in range(4):
        commande = maintenant - timedelta(days=35 - i * 9)
        lignes = [rng.choice(PRODUITS) for _ in range(rng.randint(8, 12))]
        remises = repartir_remise([Decimal(p[1]) for p in lignes], Decimal("8.00"))
        batch = Batch(nom=f"Démo {i + 1}", fournisseur="Hacoo", date_commande=commande.date(),
                      remise_globale=Decimal("8.00"), total_paye=sum(Decimal(p[1]) for p in lignes) - Decimal("8"))  # fmt: skip
        db.add(batch)
        nb["batches"] += 1
        for (nom, brut, vente), remise in zip(lignes, remises, strict=True):
            couleur = rng.choice(COULEURS)
            nom_complet = f"{nom} - {couleur}"
            net = Decimal(brut) - remise
            a = Article(
                nom=nom_complet, marque=marques.detecter_marque(nom), categorie=marques.detecter_categorie(nom),
                taille="TU" if "Bonnet" in nom or "Casquette" in nom else rng.choice(TAILLES), couleur=couleur,
                prix_achat_brut=Decimal(brut), remise=remise, prix_achat_net=net,
                prix_vente_cible=Decimal(vente), batch=batch, source="Hacoo", date_achat=commande.date(),
            )  # fmt: skip
            # Plus le batch est ancien, plus ses articles sont avancés dans le cycle.
            tirage = rng.random() + (3 - i) * 0.2
            if i == 3 and tirage < 0.5:
                statut = StatutArticle.COMMANDE
            elif tirage < 0.6:
                statut = StatutArticle.RECU_A_PUBLIER
            elif tirage < 0.9:
                statut = StatutArticle.EN_LIGNE
            else:
                statut = StatutArticle.VENDU
            a.statut = statut
            if statut != StatutArticle.COMMANDE:
                a.date_reception = commande + timedelta(days=7)
            if statut in (StatutArticle.EN_LIGNE, StatutArticle.VENDU):
                a.date_publication = commande + timedelta(days=8, hours=rng.randint(0, 48))
            db.add(a)
            db.add(HistoriqueStatut(article=a, nouveau_statut=statut, commentaire="Démo"))
            nb["articles"] += 1
            if statut == StatutArticle.VENDU and a.date_publication:
                # Date de vente répartie entre la publication et maintenant (ventes aussi cette semaine).
                ecart = max(3600.0, (maintenant - timedelta(hours=2) - a.date_publication).total_seconds())
                quand = a.date_publication + timedelta(seconds=rng.uniform(3600, ecart))
                prix = Decimal(vente) - rng.choice([Decimal(0), Decimal(0), Decimal(3)])
                a.date_vente, a.prix_vente_reel = quand, prix
                db.flush()
                v = Vente(
                    article_id=a.id, prix=prix, date_heure=quand, acheteur=f"membre_{rng.randint(10, 99)}"
                )
                db.add(v)
                db.flush()
                if maintenant - quand < timedelta(days=4):
                    db.add(
                        Envoi(
                            vente_id=v.id,
                            statut=StatutEnvoi.A_IMPRIMER,
                            date_limite_envoi=quand + timedelta(days=5),
                        )
                    )
                nb["ventes"] += 1
    db.flush()
    en_ligne = db.scalars(select(Article).where(Article.statut == StatutArticle.EN_LIGNE).limit(2)).all()
    for a in en_ligne:
        offre = (a.prix_vente_cible or Decimal("30")) * Decimal("0.7")
        db.add(Message(type="offre", acheteur="sophie.b", article_id=a.id, montant_offre=offre.quantize(Decimal("1")),
                       extrait=f"Bonjour, je te propose {offre:.0f} € pour « {a.nom} » ?", statut="a_traiter"))  # fmt: skip
    db.commit()
    return nb
