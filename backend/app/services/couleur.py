"""Contrôle de fidélité des couleurs entre une photo originale et sa version retouchée.

Couleur moyenne de la zone centrale (où se trouve le vêtement) en Lab, puis écart ΔE (CIE76).
Conversion sRGB → Lab (D65) écrite à la main : pas de dépendance lourde.
"""

import io

from PIL import Image, ImageOps

SEUIL_DELTA_E = 10.0
ZONE_CENTRALE = 0.4  # côté de la zone mesurée, en fraction de l'image
ECHANTILLON = 32  # la zone est réduite à 32 x 32 pixels avant la moyenne

# Blanc de référence D65
XN, YN, ZN = 0.95047, 1.0, 1.08883


def _lineaire(c: float) -> float:
    c /= 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _f(t: float) -> float:
    return t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29


def rgb_vers_lab(r: float, g: float, b: float) -> tuple[float, float, float]:
    rl, gl, bl = _lineaire(r), _lineaire(g), _lineaire(b)
    x = 0.4124564 * rl + 0.3575761 * gl + 0.1804375 * bl
    y = 0.2126729 * rl + 0.7151522 * gl + 0.0721750 * bl
    z = 0.0193339 * rl + 0.1191920 * gl + 0.9503041 * bl
    fx, fy, fz = _f(x / XN), _f(y / YN), _f(z / ZN)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def lab_moyen_central(contenu: bytes) -> tuple[float, float, float]:
    image = ImageOps.exif_transpose(Image.open(io.BytesIO(contenu))).convert("RGB")
    largeur, hauteur = image.size
    marge_x, marge_y = largeur * (1 - ZONE_CENTRALE) / 2, hauteur * (1 - ZONE_CENTRALE) / 2
    zone = image.crop((int(marge_x), int(marge_y), int(largeur - marge_x), int(hauteur - marge_y)))
    zone = zone.resize((ECHANTILLON, ECHANTILLON), Image.Resampling.BOX)
    pixels = [rgb_vers_lab(*zone.getpixel((x, y))) for x in range(ECHANTILLON) for y in range(ECHANTILLON)]  # type: ignore[misc]
    n = len(pixels)
    return (
        sum(p[0] for p in pixels) / n,
        sum(p[1] for p in pixels) / n,
        sum(p[2] for p in pixels) / n,
    )


def delta_e(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return float(sum((x - y) ** 2 for x, y in zip(a, b, strict=True)) ** 0.5)


def ecart(original: bytes, retouchee: bytes) -> float:
    return round(delta_e(lab_moyen_central(original), lab_moyen_central(retouchee)), 1)
