import { Boxes, FileSpreadsheet, Home, Layers, type LucideIcon, PiggyBank, Search, Settings } from "lucide-react";

export interface LienNav {
  href: string;
  libelle: string;
  icone: LucideIcon;
}

// Les pages des étapes 2 à 4 (ventes, envois, mails, annonces, messages) seront ajoutées ici.
export const NAVIGATION: { groupe?: string; liens: LienNav[] }[] = [
  { liens: [{ href: "/", libelle: "Aujourd'hui", icone: Home }] },
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
      { href: "/import", libelle: "Import / export", icone: FileSpreadsheet },
      { href: "/parametres", libelle: "Paramètres", icone: Settings },
    ],
  },
];

export function estActif(pathname: string, href: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}
