"""Lecture d'un mail brut (RFC 822 / .eml) : en-têtes, texte, HTML, pièces jointes, liens."""

import html
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email import policy
from email.message import EmailMessage
from email.parser import BytesParser
from email.utils import parseaddr, parsedate_to_datetime
from hashlib import sha256
from html.parser import HTMLParser


@dataclass
class PieceJointeBrute:
    nom: str
    mime: str
    contenu: bytes


@dataclass
class MailLu:
    message_id: str
    date: datetime | None
    expediteur: str
    sujet: str
    texte: str
    html: str
    pieces_jointes: list[PieceJointeBrute] = field(default_factory=list)
    liens: list[tuple[str, str]] = field(default_factory=list)  # (texte du lien, url)

    @property
    def texte_complet(self) -> str:
        """Texte utilisé par le classement : texte brut, ou HTML converti si absent."""
        return self.texte or html_vers_texte(self.html)


class _ExtracteurHtml(HTMLParser):
    BLOCS = {"p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4", "table", "td"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.morceaux: list[str] = []
        self.liens: list[tuple[str, str]] = []
        self._lien: str | None = None
        self._texte_lien: list[str] = []
        self._ignore = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"style", "script", "head"}:
            self._ignore += 1
        if tag in self.BLOCS:
            self.morceaux.append("\n")
        if tag == "a":
            self._lien = dict(attrs).get("href")
            self._texte_lien = []

    def handle_endtag(self, tag: str) -> None:
        if tag in {"style", "script", "head"} and self._ignore:
            self._ignore -= 1
        if tag == "a" and self._lien:
            self.liens.append((" ".join("".join(self._texte_lien).split()), self._lien))
            self._lien = None

    def handle_data(self, data: str) -> None:
        if self._ignore:
            return
        self.morceaux.append(data)
        if self._lien is not None:
            self._texte_lien.append(data)


def html_vers_texte(contenu: str) -> str:
    p = _ExtracteurHtml()
    p.feed(contenu)
    texte = html.unescape("".join(p.morceaux))
    lignes = [" ".join(ligne.split()) for ligne in texte.splitlines()]
    return "\n".join(ligne for ligne in lignes if ligne)


def liens_html(contenu: str) -> list[tuple[str, str]]:
    p = _ExtracteurHtml()
    p.feed(contenu)
    return p.liens


def _corps(msg: EmailMessage, sous_type: str) -> str:
    partie = msg.get_body(preferencelist=(sous_type,))
    if partie is None:
        return ""
    try:
        return str(partie.get_content())
    except (LookupError, UnicodeDecodeError):
        charge = partie.get_payload(decode=True)
        return charge.decode("utf-8", errors="replace") if isinstance(charge, bytes) else ""


def lire_mail(brut: bytes) -> MailLu:
    msg = BytesParser(policy=policy.default).parsebytes(brut)
    assert isinstance(msg, EmailMessage)
    date: datetime | None = None
    if msg["Date"]:
        try:
            date = parsedate_to_datetime(str(msg["Date"]))
            if date.tzinfo is None:
                date = date.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            date = None
    # Sans Message-ID (rare), on dérive un identifiant stable du contenu pour le dédoublonnage.
    message_id = str(msg["Message-ID"] or "").strip() or f"<sans-id-{sha256(brut).hexdigest()[:32]}>"
    corps_html = _corps(msg, "html")
    pieces = []
    for partie in msg.iter_attachments():
        contenu = partie.get_payload(decode=True)
        if isinstance(contenu, bytes) and contenu:
            pieces.append(
                PieceJointeBrute(
                    nom=partie.get_filename() or "piece-jointe",
                    mime=partie.get_content_type(),
                    contenu=contenu,
                )
            )
    return MailLu(
        message_id=message_id[:500],
        date=date,
        expediteur=parseaddr(str(msg["From"] or ""))[1].lower() or str(msg["From"] or ""),
        sujet=" ".join(str(msg["Subject"] or "").split()),
        texte=_corps(msg, "plain"),
        html=corps_html,
        pieces_jointes=pieces,
        liens=liens_html(corps_html) if corps_html else re_liens(_corps(msg, "plain")),
    )


def re_liens(texte: str) -> list[tuple[str, str]]:
    return [("", u) for u in re.findall(r"https?://[^\s<>\"')]+", texte)]
