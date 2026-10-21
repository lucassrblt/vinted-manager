"""Déduction de la marque, de la catégorie et de la couleur à partir du nom d'un article."""

import re
import unicodedata

# Nom canonique -> alias recherchés (en minuscules, sans accents). L'ordre compte :
# les noms les plus spécifiques d'abord (« Nike ACG » avant « Nike »).
MARQUES: list[tuple[str, list[str]]] = [
    ("Comme des Garçons Play", ["comme des garcons play", "cdg play", "comme des garcons", "cdg"]),
    ("Carhartt WIP", ["carhartt wip", "carhartt"]),
    ("Ralph Lauren", ["polo ralph lauren", "ralph lauren", "ralph"]),
    ("Patagonia", ["patagonia"]),
    ("The North Face", ["the north face", "north face", "tnf"]),
    ("Nike ACG", ["nike acg", "acg"]),
    ("Nike", ["nike"]),
    ("Lacoste", ["lacoste"]),
    ("Columbia", ["columbia"]),
    ("Dickies", ["dickies"]),
    ("Adidas", ["adidas originals", "adidas"]),
    ("Tommy Hilfiger", ["tommy hilfiger", "tommy"]),
    ("Corteiz", ["corteiz", "crtz"]),
    ("Stone Island", ["stone island"]),
    ("Arc'teryx", ["arc'teryx", "arcteryx"]),
    ("Levi's", ["levi's", "levis"]),
    ("Stüssy", ["stussy"]),
    ("Champion", ["champion"]),
    ("Fila", ["fila"]),
    ("Napapijri", ["napapijri"]),
    ("Timberland", ["timberland"]),
]

# Catégorie -> mots-clés. Le premier mot-clé trouvé (dans l'ordre de la liste) l'emporte.
CATEGORIES: list[tuple[str, list[str]]] = [
    ("T-shirt", ["t-shirt", "tshirt", "tee", "t shirt"]),
    ("Maillot", ["maillot", "jersey"]),
    ("Hoodie", ["hoodie", "sweat a capuche"]),
    ("Pull", ["pull", "sweater", "maille", "knit", "cardigan"]),
    ("Sweat", ["sweat", "crewneck"]),
    ("Bonnet", ["bonnet", "beanie"]),
    ("Casquette", ["casquette", "cap"]),
    ("Coupe-vent", ["coupe-vent", "coupe vent", "windbreaker", "shell"]),
    ("Veste", ["veste", "anorak", "jacket", "doudoune", "parka", "surchemise", "overshirt"]),
    ("Polaire", ["polaire", "fleece", "snap-t", "snap t"]),
    ("Pantalon", ["pantalon", "jean", "pant", "cargo"]),
    ("Short", ["short"]),
    ("Chemise", ["chemise", "shirt"]),
    ("Polo", ["polo"]),
]


def normaliser(texte: str) -> str:
    sans_accents = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return sans_accents.lower().replace("œ", "oe")


def _contient(texte_norm: str, alias: str) -> bool:
    return re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", texte_norm) is not None


def detecter_marque(nom: str) -> str | None:
    texte = normaliser(nom)
    for canonique, alias in MARQUES:
        if any(_contient(texte, a) for a in alias):
            return canonique
    return None


def detecter_categorie(nom: str) -> str | None:
    texte = normaliser(nom.split(" - ")[0])
    meilleure: tuple[int, str] | None = None
    for rang, (categorie, mots) in enumerate(CATEGORIES):
        for mot in mots:
            m = re.search(rf"(?<![a-z0-9]){re.escape(mot)}(?![a-z0-9])", texte)
            if m:
                # Le mot-clé le plus à gauche du nom décrit le type (« Pull demi-zip polaire » = Pull).
                cle = (m.start() * 100 + rang, categorie)
                if meilleure is None or cle < meilleure:
                    meilleure = cle
    return meilleure[1] if meilleure else None


def detecter_couleur(nom: str) -> str | None:
    if " - " not in nom:
        return None
    partie = nom.rsplit(" - ", 1)[1]
    partie = re.sub(r"\(.*?\)", "", partie).strip()
    if not partie or re.search(r"\d", partie) or "lot" in normaliser(partie).split():
        return None
    return partie[0].upper() + partie[1:].lower()
