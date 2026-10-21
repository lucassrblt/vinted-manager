import io
import random
import zipfile
from decimal import Decimal as D
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Article
from app.services import images, photos, replicate_client


def jpeg(
    largeur: int = 400, hauteur: int = 300, couleur: str = "gray", exif: Image.Exif | None = None
) -> bytes:
    tampon = io.BytesIO()
    Image.new("RGB", (largeur, hauteur), couleur).save(tampon, "JPEG", exif=exif or Image.Exif())
    return tampon.getvalue()


def test_preparation_redresse_et_retire_le_gps() -> None:
    exif = Image.Exif()
    exif[0x0112] = 6  # orientation : rotation de 90°
    exif[0x8825] = {2: (48.0, 51.0, 24.0)}  # bloc GPS
    sortie = Image.open(io.BytesIO(images.preparer(jpeg(400, 300, exif=exif))))
    assert sortie.size == (300, 400)  # redressée
    assert not sortie.getexif()  # plus aucune métadonnée


def test_preparation_reduit_et_refuse_un_fichier_invalide() -> None:
    assert max(Image.open(io.BytesIO(images.preparer(jpeg(4000, 3000)))).size) == images.TAILLE_MAX
    with pytest.raises(images.ImageInvalide):
        images.preparer(b"pas une image")


def test_prompts_par_type_et_variation() -> None:
    a = Article(nom="Sweat Uniqlo - gris", marque="Uniqlo", categorie="Sweat", couleur="Gris clair")
    devant = photos.construire_prompt("devant", a, "sleeves bent")
    assert "front side up" in devant and "sweat uniqlo gris clair" in devant and "keep any wear" in devant
    etiquette = photos.construire_prompt("etiquette", a, "close")
    assert "do not rewrite, invent" in etiquette
    dispositions = {photos.disposition("devant", random.Random(i), "light") for i in range(30)}
    assert len(dispositions) > 10  # les articles ne sont pas tous disposés pareil


@pytest.fixture
def config(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Token et faux appel Replicate qui renvoie une image orange."""
    monkeypatch.setattr(get_settings(), "replicate_api_token", "r8_test")
    appels: list[dict[str, Any]] = []

    def faux(modele: str, prompt: str, imgs: list[tuple[str, bytes]]) -> tuple[bytes, str]:
        appels.append({"modele": modele, "prompt": prompt, "nb_images": len(imgs)})
        return jpeg(600, 800, "orange"), f"pred-{len(appels)}"

    monkeypatch.setattr(replicate_client, "generer", faux)
    return appels


def _article(db: Session) -> Article:
    a = Article(
        nom="Hoodie Adidas - gris",
        marque="Adidas",
        categorie="Hoodie",
        couleur="Gris",
        prix_achat_net=D("10"),
    )
    db.add(a)
    db.commit()
    return a


def _deposer(client: TestClient, article_id: int, type_photo: str) -> dict[str, Any]:
    r = client.post(f"/api/articles/{article_id}/photos", data={"type": type_photo},
                    files={"fichier": (f"{type_photo}.jpg", jpeg(), "image/jpeg")})  # fmt: skip
    assert r.status_code == 201, r.text
    return dict(r.json())


def test_parcours_complet(client: TestClient, db: Session, config: list[dict[str, Any]]) -> None:
    a = _article(db)
    assert client.post(f"/api/articles/{a.id}/photos/generer").status_code == 409  # pas de fond
    r = client.post(
        "/api/parametres/photos/fond", files={"fichier": ("tapis.jpg", jpeg(couleur="white"), "image/jpeg")}
    )
    assert r.json()["fond_defini"] is True and r.json()["modele"] == "google/nano-banana-2"

    for t in ("devant", "dos", "etiquette", "logo", "defaut"):
        _deposer(client, a.id, t)
    etat = client.get(f"/api/articles/{a.id}/photos").json()
    assert etat["manquantes"] == []
    assert next(p for p in etat["photos"] if p["type"] == "defaut")["statut"] == "original"

    r = client.post(f"/api/articles/{a.id}/photos/generer")
    assert r.status_code == 200 and len(r.json()) == 4  # le défaut n'est jamais envoyé à l'IA
    assert len(config) == 4
    # vues entières : photo + tapis ; gros plans : + photo « devant » comme référence de couleur
    assert [c["nb_images"] for c in config] == [2, 2, 3, 3]
    assert "Image 3 shows the whole garment" in config[2]["prompt"]
    etat = client.get(f"/api/articles/{a.id}/photos").json()
    generees = [p for p in etat["photos"] if p["type"] != "defaut"]
    assert all(p["statut"] == "genere" and p["a_version_generee"] for p in generees)
    assert D(etat["cout_total"]) == D("0.268")

    devant = next(p for p in etat["photos"] if p["type"] == "devant")
    img = Image.open(io.BytesIO(client.get(f"/api/photos/{devant['id']}/fichier").content))
    assert img.getpixel((10, 10))[0] > 200  # version générée (orange)
    client.patch(f"/api/photos/{devant['id']}", json={"version_choisie": "original"})
    img = Image.open(io.BytesIO(client.get(f"/api/photos/{devant['id']}/fichier").content))
    assert img.getpixel((10, 10))[0] < 200  # retour à l'original (gris)

    r = client.post(f"/api/photos/{devant['id']}/regenerer")
    assert r.json()["statut"] == "en_cours"
    assert client.get(f"/api/articles/{a.id}/photos").json()["photos"][0]["nb_generations"] == 2

    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/articles/{a.id}/photos.zip").content))
    assert z.namelist() == ["01-devant.jpg", "02-dos.jpg", "03-etiquette.jpg", "04-logo.jpg", "05-defaut.jpg"]


def test_defaut_jamais_retouche(client: TestClient, db: Session, config: list[dict[str, Any]]) -> None:
    a = _article(db)
    p = _deposer(client, a.id, "defaut")
    assert client.post(f"/api/photos/{p['id']}/regenerer").status_code == 409
    assert client.patch(f"/api/photos/{p['id']}", json={"version_choisie": "genere"}).status_code == 409


def test_format_refuse(client: TestClient, db: Session) -> None:
    a = _article(db)
    r = client.post(f"/api/articles/{a.id}/photos", data={"type": "devant"},
                    files={"fichier": ("x.heic", b"...", "image/heic")})  # fmt: skip
    assert r.status_code == 415 and "JPG" in r.json()["detail"]


def test_erreur_replicate_marquee_sur_la_photo(
    client: TestClient, db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(get_settings(), "replicate_api_token", "r8_test")

    def echec(*_: Any) -> tuple[bytes, str]:
        raise replicate_client.ErreurReplicate("Crédit Replicate épuisé : ajoute du crédit.")

    monkeypatch.setattr(replicate_client, "generer", echec)
    a = _article(db)
    client.post("/api/parametres/photos/fond", files={"fichier": ("t.jpg", jpeg(), "image/jpeg")})
    _deposer(client, a.id, "devant")
    client.post(f"/api/articles/{a.id}/photos/generer")
    photo = client.get(f"/api/articles/{a.id}/photos").json()["photos"][0]
    assert photo["statut"] == "erreur" and "Crédit" in photo["erreur"]


def test_client_replicate_attend_la_limite_de_debit(monkeypatch: pytest.MonkeyPatch) -> None:
    """429 (peu de crédit) puis succès : on attend et on réessaie au lieu d'échouer."""
    monkeypatch.setattr(get_settings(), "replicate_api_token", "r8_test")
    monkeypatch.setattr(replicate_client.time, "sleep", lambda s: None)
    appels = {"predictions": 0}

    def gerer(requete: httpx.Request) -> httpx.Response:
        if requete.url.path == "/v1/files":
            return httpx.Response(201, json={"urls": {"get": "https://api.replicate.com/v1/files/f1"}})
        if requete.url.path.endswith("/predictions"):
            appels["predictions"] += 1
            if appels["predictions"] == 1:
                return httpx.Response(429, json={"retry_after": 1})
            return httpx.Response(
                201,
                json={
                    "id": "p1",
                    "status": "starting",
                    "urls": {"get": "https://api.replicate.com/v1/predictions/p1"},
                },
            )
        if requete.url.path == "/v1/predictions/p1":
            return httpx.Response(
                200, json={"id": "p1", "status": "succeeded", "output": "https://replicate.delivery/x.jpg"}
            )
        return httpx.Response(200, content=b"image")

    transport = httpx.MockTransport(gerer)
    original = httpx.Client
    monkeypatch.setattr(replicate_client.httpx, "Client", lambda *a, **kw: original(transport=transport))
    contenu, pid = replicate_client.generer("google/nano-banana-2", "prompt", [("a.jpg", b"x")])
    assert contenu == b"image" and pid == "p1" and appels["predictions"] == 2


def test_parametres_modele(client: TestClient) -> None:
    assert (
        client.put("/api/parametres/photos", json={"modele": "bytedance/seedream-5-lite"}).json()["modele"]
        == "bytedance/seedream-5-lite"
    )
    assert client.put("/api/parametres/photos", json={"modele": "inconnu/x"}).status_code == 422
