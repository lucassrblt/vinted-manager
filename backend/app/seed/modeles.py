"""Modèles d'annonce et de réponse par défaut, installés au premier démarrage (tables vides)."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import ModeleAnnonce, ModeleReponse

MODELES_ANNONCE = [
    ("Pull / maille", "Pull", "Pull [type] [Marque] [couleur] [taille]",
     "Pull [type] [Marque], couleur [couleur], taille [taille]. État : [état]. [Défauts éventuels]. [Mesures]. Possibilité de lot.",
     "pull, maille, [marque], [couleur]"),
    ("Hoodie / sweat", "Hoodie", "Hoodie [Marque] [couleur] [taille]",
     "Hoodie [Marque] [couleur], taille [taille]. État : [état]. [Défauts éventuels]. [Mesures]. Possibilité de lot.",
     "hoodie, sweat à capuche, [marque], streetwear"),
    ("T-shirt", "T-shirt", "T-shirt [Marque] [motif] [couleur] [taille]",
     "T-shirt [Marque] [motif], couleur [couleur], taille [taille]. État : [état]. [Défauts éventuels]. Possibilité de lot.",
     "t-shirt, tee, [marque], [couleur]"),
    ("Veste / polaire", "Veste", "[Type] [Marque] [couleur] [taille]",
     "[Type] [Marque] [couleur], taille [taille]. État : [état]. [Matière si connue]. [Défauts éventuels]. [Mesures]. Possibilité de lot.",
     "veste, polaire, outdoor, [marque]"),
    ("Accessoire", "Bonnet", "[Type] [Marque] [couleur]",
     "[Type] [Marque] [couleur], taille unique. État : [état]. Possibilité de lot.",
     "bonnet, casquette, accessoire, [marque]"),
]  # fmt: skip

MODELES_REPONSE = [
    ("Remerciement après achat", "remerciement",
     "Merci beaucoup pour ton achat ! Je prépare ton colis et je l'envoie au plus vite. Belle journée !"),
    ("Demande de lot", "demande de lot",
     "Avec plaisir pour un lot ! Ajoute les articles qui t'intéressent à un lot et je te fais une petite réduction."),
    ("Question sur la taille", "question taille",
     "Bonjour ! Il taille plutôt normalement. Je peux te donner les mesures à plat si tu veux comparer avec un de tes vêtements."),
    ("Offre trop basse", "offre trop basse",
     "Merci pour ton offre ! Je ne peux malheureusement pas descendre autant, mais je peux faire un petit geste si tu veux."),
    ("Toujours disponible", "toujours disponible",
     "Bonjour, oui il est toujours disponible ! N'hésite pas si tu as une question."),
]  # fmt: skip


def installer_modeles(db: Session) -> None:
    if not db.scalar(select(func.count(ModeleAnnonce.id))):
        for nom, categorie, titre, description, mots in MODELES_ANNONCE:
            db.add(ModeleAnnonce(nom=nom, categorie=categorie, structure_titre=titre,
                                 structure_description=description, mots_cles=mots))  # fmt: skip
    if not db.scalar(select(func.count(ModeleReponse.id))):
        for nom, contexte, texte in MODELES_REPONSE:
            db.add(ModeleReponse(nom=nom, contexte=contexte, texte=texte))
    db.commit()
