// Formats français, fuseau Europe/Paris partout.
export const TZ = "Europe/Paris";

const euros = new Intl.NumberFormat("fr-FR", { style: "currency", currency: "EUR" });
const nombre = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 2 });
const pourcent = new Intl.NumberFormat("fr-FR", { style: "percent", maximumFractionDigits: 1 });
const dateCourte = new Intl.DateTimeFormat("fr-FR", {
  timeZone: TZ,
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
});
const dateHeure = new Intl.DateTimeFormat("fr-FR", {
  timeZone: TZ,
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});

type Num = number | string | null | undefined;

export function num(v: Num): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : null;
}

/** 1 234,50 € — ou « — » si vide. */
export function formatEuros(v: Num): string {
  const n = num(v);
  return n === null ? "—" : euros.format(n);
}

export function formatNombre(v: Num, decimales = 2): string {
  const n = num(v);
  if (n === null) return "—";
  return decimales === 2 ? nombre.format(n) : n.toLocaleString("fr-FR", { maximumFractionDigits: decimales });
}

export function formatPourcent(v: Num): string {
  const n = num(v);
  return n === null ? "—" : pourcent.format(n);
}

export function formatCoefficient(v: Num): string {
  const n = num(v);
  return n === null ? "—" : `×${n.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** Date seule « AAAA-MM-JJ » (sans fuseau) ou date-heure ISO -> JJ/MM/AAAA. */
export function formatDate(v: string | null | undefined): string {
  if (!v) return "—";
  if (/^\d{4}-\d{2}-\d{2}$/.test(v)) {
    const [a, m, j] = v.split("-");
    return `${j}/${m}/${a}`;
  }
  return dateCourte.format(new Date(v));
}

export function formatDateHeure(v: string | null | undefined): string {
  if (!v) return "—";
  return dateHeure.format(new Date(v)).replace(" ", " à ");
}

export function formatDelai(heures: number | null | undefined): string {
  if (heures === null || heures === undefined) return "—";
  if (heures < 24) return `${Math.round(heures)} h`;
  const jours = heures / 24;
  return `${jours.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} j`;
}

/** Date du jour à Paris au format AAAA-MM-JJ. */
export function aujourdhuiParis(): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date());
}

/** Convertit une saisie française (« 12,50 ») en chaîne décimale pour l'API (« 12.50 »). */
export function saisieVersDecimal(v: string): string | null {
  const propre = v.replace(/\s|€/g, "").replace(",", ".");
  if (propre === "") return null;
  return Number.isFinite(Number(propre)) ? propre : null;
}

/** Jour (AAAA-MM-JJ) à Paris d'une date-heure ISO. */
export function jourParis(iso: string): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ }).format(new Date(iso));
}

/** Échéance relative à aujourd'hui (heure de Paris) : retard, aujourd'hui, demain ou plus tard. */
export function echeance(iso: string | null | undefined): "retard" | "aujourdhui" | "demain" | "plus_tard" | null {
  if (!iso) return null;
  const jour = jourParis(iso);
  const auj = aujourdhuiParis();
  const demain = new Date(`${auj}T12:00:00Z`);
  demain.setUTCDate(demain.getUTCDate() + 1);
  if (jour < auj) return "retard";
  if (jour === auj) return "aujourdhui";
  if (jour === demain.toISOString().slice(0, 10)) return "demain";
  return "plus_tard";
}
