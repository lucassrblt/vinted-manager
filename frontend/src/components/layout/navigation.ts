import {
  Boxes,
  FileSpreadsheet,
  Filter,
  Home,
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

// Les pages des étapes 3 et 4 (annonces, messages) seront ajoutées ici.
export const NAVIGATION: { groupe?: string; liens: LienNav[] }[] = [
  { liens: [{ href: "/", libelle: "Aujourd'hui", icone: Home }] },
  {
    groupe: "Ventes",
    liens: [
      { href: "/envois", libelle: "Envois", icone: Truck },
      { href: "/ventes", libelle: "Ventes", icone: Receipt },
      { href: "/mails", libelle: "Mails", icone: Inbox },
    ],
  },
  {
    groupe: "Stock",
    liens: [
      { href: "/stock", libelle: "Articles", icone: Boxes },
      { href: "/batches", libelle: "Batches", icone: Layers },
      { href: "/sourcing", libelle: "Sourcing", icone: Search },
    ],
  },
  {
    groupe: "Gestion",
    liens: [
      { href: "/compta", libelle: "Compta", icone: PiggyBank },
      { href: "/regles", libelle: "Règles des mails", icone: Filter },
      { href: "/import", libelle: "Import / export", icone: FileSpreadsheet },
      { href: "/parametres", libelle: "Paramètres", icone: Settings },
    ],
  },
];

export function estActif(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}
