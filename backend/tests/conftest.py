import os
from collections.abc import Iterator
from pathlib import Path

import pytest

# À définir avant tout import de l'application (le moteur SQLAlchemy est créé à l'import).
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://vm:vm@localhost:54329/vm_test"
)
os.environ["COOKIE_SECURE"] = "false"
os.environ["SCHEDULER_ACTIF"] = "false"
os.environ.setdefault("FERNET_KEY", "x8J6c9n8Wq2N3bJ5cT0E7jQ4oX1hY2bV6aZ9kL3mP0s=")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.config import get_settings  # noqa: E402
from app.db import Base, SessionLocal, engine  # noqa: E402
from app.models import Utilisateur  # noqa: E402
from app.services.auth import hasher_mot_de_passe  # noqa: E402

EXCEL_REEL = Path(os.environ.get("EXCEL_REEL", Path(__file__).parent / "data" / "suivi-revente.xlsx"))
EMAIL = "moi@example.com"
MOT_DE_PASSE = "motdepasse-solide"


@pytest.fixture(scope="session", autouse=True)
def schema() -> Iterator[None]:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield


@pytest.fixture(autouse=True)
def base_vide(tmp_path: Path) -> Iterator[None]:
    get_settings().data_dir = tmp_path
    yield
    tables = ", ".join(t.name for t in Base.metadata.sorted_tables)
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))


@pytest.fixture
def db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


@pytest.fixture
def anonyme() -> TestClient:
    from app.main import app

    return TestClient(app)


@pytest.fixture
def client(db: Session) -> TestClient:
    from app.main import app

    db.add(Utilisateur(email=EMAIL, mot_de_passe_hash=hasher_mot_de_passe(MOT_DE_PASSE)))
    db.commit()
    c = TestClient(app)
    r = c.post("/api/auth/login", json={"email": EMAIL, "mot_de_passe": MOT_DE_PASSE})
    assert r.status_code == 200, r.text
    return c


@pytest.fixture
def excel_reel() -> bytes:
    if not EXCEL_REEL.exists():
        pytest.skip(f"Excel réel absent ({EXCEL_REEL}) : copie-le dans tests/data/suivi-revente.xlsx")
    return EXCEL_REEL.read_bytes()


@pytest.fixture
def regles(db: Session) -> None:
    from app.seed.regles import installer_regles

    installer_regles(db)
