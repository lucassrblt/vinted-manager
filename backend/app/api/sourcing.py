from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import Db
from app.models import PisteSourcing
from app.schemas.stock import PisteIn, PisteOut, PisteUpdate
from app.services import stats

router = APIRouter(prefix="/sourcing", tags=["sourcing"])


def _avec_perf(piste: PisteSourcing, perf: stats.Perf) -> PisteOut:
    out = PisteOut.model_validate(piste)
    out.perf_nb_ventes = perf.nb_ventes
    out.perf_prix_moyen = perf.prix_moyen
    out.perf_delai_moyen_jours = perf.delai_moyen_jours
    out.perf_coefficient_moyen = perf.coefficient_moyen
    out.perf_base = perf.base
    return out


@router.get("", response_model=list[PisteOut])
def lister(db: Db) -> list[PisteOut]:
    pistes = list(db.scalars(select(PisteSourcing).order_by(PisteSourcing.origine, PisteSourcing.id)))
    perfs = stats.perf_pistes(db, pistes)
    return [_avec_perf(p, perfs[p.id]) for p in pistes]


@router.post("", response_model=PisteOut, status_code=201)
def creer(data: PisteIn, db: Db) -> PisteOut:
    piste = PisteSourcing(**data.model_dump(), origine="manuel")
    db.add(piste)
    db.commit()
    db.refresh(piste)
    return _avec_perf(piste, stats.perf_pistes(db, [piste])[piste.id])


@router.patch("/{piste_id}", response_model=PisteOut)
def modifier(piste_id: int, data: PisteUpdate, db: Db) -> PisteOut:
    piste = db.get(PisteSourcing, piste_id)
    if piste is None:
        raise HTTPException(404, "Piste introuvable.")
    for cle, valeur in data.model_dump(exclude_unset=True).items():
        setattr(piste, cle, valeur)
    db.commit()
    db.refresh(piste)
    return _avec_perf(piste, stats.perf_pistes(db, [piste])[piste.id])


@router.delete("/{piste_id}", status_code=204)
def supprimer(piste_id: int, db: Db) -> None:
    piste = db.get(PisteSourcing, piste_id)
    if piste is None:
        raise HTTPException(404, "Piste introuvable.")
    db.delete(piste)
    db.commit()
