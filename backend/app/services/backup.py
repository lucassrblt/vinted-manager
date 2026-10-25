"""Sauvegarde complète : export Excel + dump JSON de toutes les tables + fichiers du volume."""

import json
import tempfile
import zipfile
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import Base, utcnow
from app.models import Parametres
from app.services import excel_export, storage
from app.services.stats import tz

# Jamais dans la sauvegarde : secrets et données de session.
COLONNES_EXCLUES = {
    "utilisateur": {"mot_de_passe_hash"},
    "compte_vinted": {"imap_mot_de_passe_chiffre", "jeton_extension_hash"},
}
TABLES_EXCLUES = {"session_utilisateur", "tentative_connexion"}


def _json(v: Any) -> Any:
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, datetime | date):
        return v.isoformat()
    return v


def dump_json(db: Session) -> dict[str, list[dict[str, Any]]]:
    donnees: dict[str, list[dict[str, Any]]] = {}
    for table in Base.metadata.sorted_tables:
        if table.name in TABLES_EXCLUES:
            continue
        exclues = COLONNES_EXCLUES.get(table.name, set())
        colonnes = [c for c in table.columns if c.name not in exclues]
        lignes = db.execute(select(*colonnes)).mappings().all()
        donnees[table.name] = [{k: _json(v) for k, v in ligne.items()} for ligne in lignes]
    return donnees


def generer(db: Session, params: Parametres) -> Path:
    """Écrit le zip dans un fichier temporaire (les fichiers du volume peuvent être volumineux)."""
    horodatage = f"{utcnow().astimezone(tz()):%Y%m%d-%H%M}"
    chemin = Path(tempfile.gettempdir()) / f"sauvegarde-revente-{horodatage}.zip"
    with zipfile.ZipFile(chemin, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(f"suivi-revente-{horodatage}.xlsx", excel_export.generer_export(db, params))
        z.writestr("base.json", json.dumps(dump_json(db), ensure_ascii=False, indent=1))
        racine = storage.racine()
        if racine.exists():
            for fichier in sorted(racine.rglob("*")):
                if fichier.is_file():
                    z.write(fichier, f"fichiers/{fichier.relative_to(racine)}")
        z.writestr(
            "LISEZMOI.txt",
            "Sauvegarde complète de l'app Revente.\n"
            "- suivi-revente-*.xlsx : export Excel (même structure que l'Excel d'origine)\n"
            "- base.json : toutes les tables (sans mots de passe ni sessions)\n"
            "- fichiers/ : preuves d'achat, bordereaux et pièces jointes des mails\n",
        )
    return chemin
