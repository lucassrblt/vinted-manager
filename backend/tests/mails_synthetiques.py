"""Mails Vinted synthétiques (formulations plausibles) pour tester le moteur de règles.

Ils ne remplacent pas les vrais .eml de backend/fixtures/emails/ : ils garantissent seulement que
le pipeline fonctionne. Les règles initiales seront ajustées sur les vrais mails.
"""

import io
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime

from pypdf import PdfWriter

DATE = datetime(2026, 10, 20, 14, 32, tzinfo=UTC)


def pdf_vierge(largeur: float = 595, hauteur: float = 842) -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=largeur, height=hauteur)
    tampon = io.BytesIO()
    w.write(tampon)
    return tampon.getvalue()


def mail(
    sujet: str,
    texte: str,
    html: str | None = None,
    pdf: bytes | None = None,
    message_id: str | None = None,
    expediteur: str = "Vinted <no-reply@vinted.fr>",
    date: datetime = DATE,
) -> bytes:
    m = EmailMessage()
    m["From"] = expediteur
    m["To"] = "moi@example.com"
    m["Subject"] = sujet
    m["Date"] = format_datetime(date)
    m["Message-ID"] = message_id or f"<{abs(hash((sujet, texte)))}@vinted.fr>"
    m.set_content(texte)
    if html:
        m.add_alternative(html, subtype="html")
    if pdf:
        m.add_attachment(pdf, maintype="application", subtype="pdf", filename="bordereau.pdf")
    return bytes(m)


VENTE = mail(
    "Ton article a été vendu !",
    "Bonne nouvelle ! claire_75 a acheté ton article « Pull demi-zip polaire Ralph Lauren - Noir ».\n"
    "Prix : 45,00 €\nCommande n° 8812345678\n"
    "Envoie-le avant le 27/10/2026 avec le bordereau d'envoi.",
    html="<p>claire_75 a acheté ton article « Pull demi-zip polaire Ralph Lauren - Noir ».</p>"
    "<p>Prix : 45,00 €</p><p>Commande n° 8812345678</p>"
    '<p>Envoie-le avant le 27/10/2026.</p><a href="https://www.vinted.fr/shipping/label/123">Télécharger le bordereau</a>',
)

BORDEREAU = mail(
    "Ton bordereau d'envoi est prêt",
    "Voici le bordereau pour la commande n° 8812345678 : article « Pull demi-zip polaire Ralph Lauren - Noir ».",
    pdf=pdf_vierge(),
)

EXPEDIE = mail(
    "Ton colis a été déposé",
    "Le colis de la commande n° 8812345678 a été pris en charge par le transporteur.",
)

LIVRE = mail(
    "Ton colis a été livré",
    "La commande n° 8812345678 (article « Pull demi-zip polaire Ralph Lauren - Noir ») a été livrée.",
)

LITIGE = mail(
    "Un problème avec ta commande a été signalé",
    "L'acheteur a signalé un problème avec l'article « Pull demi-zip polaire Ralph Lauren - Noir ». "
    "Commande n° 8812345678.",
)

OFFRE = mail(
    "Nouvelle offre sur ton article",
    "Membre : sophie.b te propose 35,00 € pour ton article « Pull demi-zip polaire Ralph Lauren - Tibet ».",
)

MESSAGE = mail(
    "Tu as reçu un nouveau message",
    "Membre : tom_r\nÀ propos de l'article « Bonnet Ralph Lauren - Blanc » : il est toujours dispo ?",
)

ARGENT = mail("Ton argent est disponible", "45,00 € ont été ajoutés à ton porte-monnaie Vinted.")

EVALUATION = mail("Tu as reçu une nouvelle évaluation", "Membre : claire_75 t'a laissé 5 étoiles.")

INCONNU = mail("Les tendances de la semaine", "Découvre les nouveautés de la communauté.")

PAR_TYPE = {
    "vente": VENTE,
    "bordereau": BORDEREAU,
    "expedie": EXPEDIE,
    "livre": LIVRE,
    "litige": LITIGE,
    "offre": OFFRE,
    "message": MESSAGE,
    "argent_disponible": ARGENT,
    "evaluation": EVALUATION,
}
