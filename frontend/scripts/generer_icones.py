"""Génère les icônes PWA (PNG) : t-shirt blanc sur fond vert sauge. Sans dépendance.

    python3 scripts/generer_icones.py
"""

import struct
import zlib
from pathlib import Path

FOND = (47, 127, 110)  # vert sauge (accent de l'app)
BLANC = (255, 255, 255)
SORTIE = Path(__file__).resolve().parent.parent / "public" / "icons"

# T-shirt dans un repère 0..1 (polygone)
TSHIRT = [
    (0.36, 0.22), (0.43, 0.22), (0.46, 0.27), (0.54, 0.27), (0.57, 0.22), (0.64, 0.22),
    (0.80, 0.33), (0.73, 0.45), (0.66, 0.41), (0.66, 0.78), (0.34, 0.78), (0.34, 0.41),
    (0.27, 0.45), (0.20, 0.33),
]


def dans_polygone(x: float, y: float, poly: list[tuple[float, float]]) -> bool:
    dedans = False
    j = len(poly) - 1
    for i, (xi, yi) in enumerate(poly):
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            dedans = not dedans
        j = i
    return dedans


def dans_coins_arrondis(x: float, y: float, rayon: float) -> bool:
    cx = min(max(x, rayon), 1 - rayon)
    cy = min(max(y, rayon), 1 - rayon)
    return (x - cx) ** 2 + (y - cy) ** 2 <= rayon**2


def png(taille: int, echelle: float, rayon: float) -> bytes:
    ss = 4  # sur-échantillonnage pour lisser les bords
    lignes = bytearray()
    poly = [(0.5 + (px - 0.5) * echelle, 0.5 + (py - 0.5) * echelle) for px, py in TSHIRT]
    for py in range(taille):
        lignes.append(0)
        for px in range(taille):
            r = g = b = a = 0.0
            for sy in range(ss):
                for sx in range(ss):
                    x = (px + (sx + 0.5) / ss) / taille
                    y = (py + (sy + 0.5) / ss) / taille
                    if rayon and not dans_coins_arrondis(x, y, rayon):
                        continue
                    c = BLANC if dans_polygone(x, y, poly) else FOND
                    r, g, b, a = r + c[0], g + c[1], b + c[2], a + 255
            n = ss * ss
            alpha = a / n
            if alpha:
                lignes += bytes((round(r / (a / 255)), round(g / (a / 255)), round(b / (a / 255)), round(alpha)))
            else:
                lignes += b"\0\0\0\0"

    def bloc(type_: bytes, donnees: bytes) -> bytes:
        return struct.pack(">I", len(donnees)) + type_ + donnees + struct.pack(">I", zlib.crc32(type_ + donnees) & 0xFFFFFFFF)

    entete = struct.pack(">IIBBBBB", taille, taille, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + bloc(b"IHDR", entete) + bloc(b"IDAT", zlib.compress(bytes(lignes), 9)) + bloc(b"IEND", b"")


if __name__ == "__main__":
    SORTIE.mkdir(parents=True, exist_ok=True)
    # Icônes « any » : coins arrondis ; « maskable » et Apple : plein cadre, motif réduit (zone sûre).
    for nom, taille, echelle, rayon in (
        ("icon-192.png", 192, 1.0, 0.22),
        ("icon-512.png", 512, 1.0, 0.22),
        ("icon-maskable-512.png", 512, 0.78, 0),
        ("apple-touch-icon.png", 180, 0.9, 0),
        ("favicon-32.png", 32, 1.15, 0.22),
    ):
        (SORTIE / nom).write_bytes(png(taille, echelle, rayon))
        print("écrit", nom)
