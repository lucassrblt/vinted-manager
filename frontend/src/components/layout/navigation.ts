import {
  BookText,
  Boxes,
  Megaphone,
  MessageCircle,
  FileSpreadsheet,
  Filter,
  Home,
  ImagePlus,
  Inbox,
  Layers,
  type LucideIcon,
  PiggyBank,
  Receipt,
  Search,
  Settings,
  Truck,
} from "lucide-react";

export interface LienNav {
  href: string;
  libelle: string;
  icone: LucideIcon;
}

export const NAVIGATION: { groupe?: string; liens: LienNav[] }[] = [
  { liens: [{ href: "/", libelle: "Aujourd'hui", icone: Home }] },
  {
    groupe: "Ventes",
    liens: [
      { href: "/envois", libelle: "Envois", icone: Truck },
      { href: "/ventes", libelle: "Ventes", icone: Receipt },
      { href: "/messages", libelle: "Messages", icone: MessageCircle },
      { href: "/mails", libelle: "Mails", icone: Inbox },
    ],
  },
  {
    groupe: "Stock",
    liens: [
      { href: "/annonces/nouvelle", libelle: "Nouvelle annonce", icone: ImagePlus },
      { href: "/stock", libelle: "Articles", icone: Boxes },
      { href: "/annonces", libelle: "Annonces", icone: Megaphone },
      { href: "/batches", libelle: "Batches", icone: Layers },
      { href: "/sourcing", libelle: "Sourcing", icone: Search },
    ],
  },
  {
    groupe: "Gestion",
    liens: [
      { href: "/compta", libelle: "Compta", icone: PiggyBank },
      { href: "/modeles", libelle: "Modèles", icone: BookText },
      { href: "/regles", libelle: "Règles des mails", icone: Filter },
      { href: "/import", libelle: "Import / export", icone: FileSpreadsheet },
      { href: "/parametres", libelle: "Paramètres", icone: Settings },
    ],
  },
];

function correspond(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}

const HREFS = NAVIGATION.flatMap((g) => g.liens.map((l) => l.href));

/** Lien actif : le plus précis qui correspond (« /annonces/nouvelle » n'allume pas « /annonces »). */
export function estActif(pathname: string, href: string): boolean {
  return correspond(pathname, href) && !HREFS.some((h) => h.length > href.length && correspond(pathname, h));
}
