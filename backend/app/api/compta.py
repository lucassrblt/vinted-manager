import csv
import io
import re
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.api.deps import Db, get_parametres
from app.services import stats

router = APIRouter(prefix="/compta", tags=["compta"])


def _montant_fr(v: Decimal) -> str:
    return f"{v:.2f}".replace(".", ",")


@router.get("/kpis", response_model=stats.Kpis)
def kpis(db: Db, du: date | None = None, au: date | None = None) -> stats.Kpis:
    return stats.kpis(stats.tous_les_articles(db), get_parametres(db), du, au)


@router.get("/series", response_model=list[stats.PointSerie])
def series(
    db: Db,
    granularite: Literal["semaine", "mois"] = "semaine",
    du: date | None = None,
    au: date | None = None,
) -> list[stats.PointSerie]:
    return stats.series(stats.tous_les_articles(db), granularite, du, au)


@router.get("/repartition")
def repartition(
    db: Db, du: date | None = None, au: date | None = None
) -> dict[str, list[stats.LigneRepartition]]:
    articles = stats.tous_les_articles(db)
    return {
        "marques": stats.repartition(articles, "marque", du, au),
        "categories": stats.repartition(articles, "categorie", du, au),
    }


@router.get("/urssaf.csv")
def urssaf(db: Db, mois: str) -> Response:
    """CSV mensuel pour la déclaration URSSAF : date, article, montant encaissé, puis le total."""
    m = re.fullmatch(r"(\d{4})-(\d{2})", mois)
    if not m or not 1 <= int(m.group(2)) <= 12:
        raise HTTPException(422, "Mois invalide (format attendu : AAAA-MM).")
    annee, num = int(m.group(1)), int(m.group(2))
    lignes = stats.lignes_urssaf(stats.tous_les_articles(db), annee, num)
    tampon = io.StringIO()
    # Point-virgule et virgule décimale : s'ouvre directement dans Excel en français.
    w = csv.writer(tampon, delimiter=";")
    w.writerow(["Date", "Article", "Montant encaissé (€)"])
    total = Decimal("0")
    for j, nom, montant in lignes:
        w.writerow([j.strftime("%d/%m/%Y"), nom, _montant_fr(montant)])
        total += montant
    w.writerow([])
    w.writerow(["Total du mois", f"{len(lignes)} vente(s)", _montant_fr(total)])
    contenu = "﻿" + tampon.getvalue()  # BOM pour les accents dans Excel
    return Response(
        contenu,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="urssaf-{mois}.csv"'},
    )
