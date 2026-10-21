"""Fusion des bordereaux PDF en un seul fichier, avec option 10x15 cm pour imprimante thermique."""

import io

from pypdf import PageObject, PdfReader, PdfWriter, Transformation

# 10 x 15 cm en points PDF (1 pt = 1/72 pouce)
LARGEUR_10X15 = 100 / 25.4 * 72
HAUTEUR_10X15 = 150 / 25.4 * 72
MARGE = 4.0


def _vers_10x15(page: PageObject) -> PageObject:
    """Met la page à l'échelle (et la tourne si elle est en paysage) pour tenir sur 10x15 cm."""
    largeur = float(page.mediabox.width)
    hauteur = float(page.mediabox.height)
    rotation = largeur > hauteur
    if rotation:
        largeur, hauteur = hauteur, largeur
    echelle = min((LARGEUR_10X15 - 2 * MARGE) / largeur, (HAUTEUR_10X15 - 2 * MARGE) / hauteur)
    dx = (LARGEUR_10X15 - largeur * echelle) / 2
    dy = (HAUTEUR_10X15 - hauteur * echelle) / 2
    # Ramène l'origine en (0, 0), tourne de 90° si besoin (x, y) -> (-y, x) puis recale, met à l'échelle et centre.
    t = Transformation().translate(-float(page.mediabox.left), -float(page.mediabox.bottom))
    if rotation:
        t = t.rotate(90).translate(float(page.mediabox.height), 0)
    t = t.scale(echelle, echelle).translate(dx, dy)
    cible = PageObject.create_blank_page(width=LARGEUR_10X15, height=HAUTEUR_10X15)
    cible.merge_transformed_page(page, t)
    return cible


def fusionner(contenus: list[bytes], format_10x15: bool = False) -> bytes:
    writer = PdfWriter()
    for contenu in contenus:
        for page in PdfReader(io.BytesIO(contenu)).pages:
            writer.add_page(_vers_10x15(page) if format_10x15 else page)
    tampon = io.BytesIO()
    writer.write(tampon)
    return tampon.getvalue()
