from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import utcnow
from app.models import SessionUtilisateur, TentativeConnexion, Utilisateur
from app.services.auth import COOKIE_SESSION, hasher_mot_de_passe
from tests.conftest import EMAIL, MOT_DE_PASSE


def _creer_user(db: Session) -> None:
    db.add(Utilisateur(email=EMAIL, mot_de_passe_hash=hasher_mot_de_passe(MOT_DE_PASSE)))
    db.commit()


def test_routes_protegees(anonyme: TestClient) -> None:
    for url in ("/api/articles", "/api/compta/kpis", "/api/batches", "/api/auth/me"):
        assert anonyme.get(url).status_code == 401
    assert anonyme.get("/health").status_code == 200


def test_login_cookie(anonyme: TestClient, db: Session) -> None:
    _creer_user(db)
    r = anonyme.post("/api/auth/login", json={"email": "MOI@example.com ", "mot_de_passe": MOT_DE_PASSE})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=lax" in cookie and "max-age=2592000" in cookie
    assert anonyme.get("/api/auth/me").json() == {"email": EMAIL}
    # Le token est stocké hashé, jamais en clair
    session = db.scalar(select(SessionUtilisateur))
    assert session is not None and session.token_hash != anonyme.cookies.get(COOKIE_SESSION)


def test_mauvais_mot_de_passe(anonyme: TestClient, db: Session) -> None:
    _creer_user(db)
    r = anonyme.post("/api/auth/login", json={"email": EMAIL, "mot_de_passe": "faux"})
    assert r.status_code == 401
    assert r.json()["detail"] == "Email ou mot de passe incorrect."


def test_blocage_apres_5_echecs(anonyme: TestClient, db: Session) -> None:
    _creer_user(db)
    for _ in range(5):
        assert anonyme.post("/api/auth/login", json={"email": EMAIL, "mot_de_passe": "x"}).status_code == 401
    # Même le bon mot de passe est refusé pendant le blocage
    r = anonyme.post("/api/auth/login", json={"email": EMAIL, "mot_de_passe": MOT_DE_PASSE})
    assert r.status_code == 429
    assert "15 minute" in r.json()["detail"]

    # 15 minutes plus tard, c'est débloqué
    for t in db.scalars(select(TentativeConnexion)):
        t.date = t.date - timedelta(minutes=16)
    db.commit()
    assert (
        anonyme.post("/api/auth/login", json={"email": EMAIL, "mot_de_passe": MOT_DE_PASSE}).status_code
        == 200
    )


def test_session_expiree(client: TestClient, db: Session) -> None:
    session = db.scalar(select(SessionUtilisateur))
    assert session is not None
    session.expires_at = utcnow() - timedelta(seconds=1)
    db.commit()
    assert client.get("/api/articles").status_code == 401


def test_session_renouvelee_a_lusage(client: TestClient, db: Session) -> None:
    session = db.scalar(select(SessionUtilisateur))
    assert session is not None
    session.expires_at = utcnow() + timedelta(days=2)
    db.commit()
    assert client.get("/api/articles").status_code == 200
    db.refresh(session)
    assert session.expires_at > utcnow() + timedelta(days=29)


def test_logout(client: TestClient) -> None:
    assert client.post("/api/auth/logout").status_code == 204
    assert client.get("/api/articles").status_code == 401
