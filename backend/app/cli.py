"""Commandes d'administration.

python -m app.cli create-user            # crée l'utilisateur (demande email + mot de passe)
python -m app.cli reset-password         # change le mot de passe
python -m app.cli vapid-keys             # génère les clés des notifications push
python -m app.cli seed-demo              # remplit une base vide avec des données de démonstration
"""

import argparse
import getpass
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import Utilisateur
from app.services.auth import hasher_mot_de_passe, nb_utilisateurs

LONGUEUR_MIN = 10


def _demander_mot_de_passe() -> str:
    while True:
        mdp = getpass.getpass("Mot de passe : ")
        if len(mdp) < LONGUEUR_MIN:
            print(f"Le mot de passe doit faire au moins {LONGUEUR_MIN} caractères.")
            continue
        if mdp != getpass.getpass("Confirmation : "):
            print("Les deux saisies ne correspondent pas.")
            continue
        return mdp


def create_user(email: str | None) -> int:
    with SessionLocal() as db:
        if nb_utilisateurs(db) > 0:
            print("Un utilisateur existe déjà (application mono-utilisateur). Utilise reset-password.")
            return 1
        email = (email or input("Email : ")).strip().lower()
        if "@" not in email:
            print("Email invalide.")
            return 1
        db.add(Utilisateur(email=email, mot_de_passe_hash=hasher_mot_de_passe(_demander_mot_de_passe())))
        db.commit()
    print(f"Utilisateur {email} créé.")
    return 0


def reset_password() -> int:
    with SessionLocal() as db:
        user = db.scalar(select(Utilisateur))
        if user is None:
            print("Aucun utilisateur. Lance d'abord create-user.")
            return 1
        user.mot_de_passe_hash = hasher_mot_de_passe(_demander_mot_de_passe())
        db.commit()
    print("Mot de passe modifié.")
    return 0


def vapid_keys() -> int:
    from app.services.push import generer_cles

    publique, privee = generer_cles()
    print("À ajouter aux variables d'environnement du backend :")
    print(f"VAPID_PUBLIC_KEY={publique}")
    print(f"VAPID_PRIVATE_KEY={privee}")
    print("VAPID_SUBJECT=mailto:ton-adresse@example.com")
    return 0


def seed_demo() -> int:
    from app.seed.demo import installer_demo

    with SessionLocal() as db:
        try:
            resume = installer_demo(db)
        except ValueError as exc:
            print(exc)
            return 1
    print(f"Données de démonstration installées : {resume}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="commande", required=True)
    cu = sub.add_parser("create-user", help="Créer l'utilisateur unique")
    cu.add_argument("--email")
    sub.add_parser("reset-password", help="Changer le mot de passe")
    sub.add_parser("vapid-keys", help="Générer les clés VAPID des notifications push")
    sub.add_parser("seed-demo", help="Installer des données de démonstration (base vide uniquement)")
    args = parser.parse_args()
    if args.commande == "create-user":
        return create_user(args.email)
    if args.commande == "vapid-keys":
        return vapid_keys()
    if args.commande == "seed-demo":
        return seed_demo()
    return reset_password()


if __name__ == "__main__":
    sys.exit(main())
