/**
 * Correspondance entre la fiche vinted-manager et les listes de Vinted (taille, marque, couleur,
 * matière). Règle : ne jamais deviner. Une valeur absente produit une erreur claire.
 */
import { normaliser } from "../outils";
import { ErreurAction } from "./erreurs";
import type { Attribut, Couleur, Marque, OptionAttribut, SuggestionsAttributs } from "./client";

export function optionsAplaties(options: OptionAttribut[] | undefined): OptionAttribut[] {
  const resultat: OptionAttribut[] = [];
  for (const o of options ?? []) {
    if (o.type === "group" || (o.options && o.options.length)) resultat.push(...optionsAplaties(o.options));
    else resultat.push(o);
  }
  return resultat;
}

export function attribut(attributs: Attribut[], code: string): Attribut | undefined {
  return attributs.find((a) => a.code === code);
}

const SYNONYMES_TAILLE: Record<string, string> = {
  tu: "taille unique",
  unique: "taille unique",
  "one size": "taille unique",
  xxl: "xxl",
  "2xl": "xxl",
  "3xl": "xxxl",
};

/** Taille de la fiche cherchée telle quelle dans les options de la catégorie. */
export function trouverTaille(attributs: Attribut[], taille: string | null): number {
  const options = optionsAplaties(attribut(attributs, "size")?.configuration?.options);
  if (!taille) throw new ErreurAction("Taille manquante sur la fiche de l'article.");
  let cible = normaliser(taille).replace(/^taille /, "");
  cible = SYNONYMES_TAILLE[cible] ?? cible;
  const trouvee = options.find((o) => normaliser(o.title) === cible);
  if (!trouvee) throw new ErreurAction(`Taille introuvable : « ${taille} » n'existe pas dans cette catégorie Vinted.`);
  return trouvee.id;
}

export function verifierEtat(attributs: Attribut[], conditionId: number): number {
  const options = optionsAplaties(attribut(attributs, "condition")?.configuration?.options);
  if (!options.some((o) => o.id === conditionId)) {
    throw new ErreurAction(`État (condition_id ${conditionId}) non proposé par Vinted pour cette catégorie.`);
  }
  return conditionId;
}

function compacte(texte: string): string {
  return normaliser(texte).replace(/ /g, "");
}

/**
 * La marque de vinted-manager prime (titre exact dans les suggestions, puis dans la liste de la
 * catégorie). Sans marque sur la fiche, la marque pré-remplie par Vinted est reprise (Lucas relit le
 * brouillon). Une marque de la fiche que Vinted ne connaît pas : erreur, jamais une autre marque.
 */
export function choisirMarque(
  marque: string | null,
  suggestions: SuggestionsAttributs,
  listeCategorie: Marque[] | null,
): Marque {
  const prefill = suggestions.prefill_brand ?? null;
  if (!marque) {
    if (prefill) return prefill;
    throw new ErreurAction("Marque manquante sur la fiche et aucune marque proposée par Vinted.");
  }
  const cible = compacte(marque);
  const exacte = [...(suggestions.brands ?? []), ...(listeCategorie ?? [])].find((b) => compacte(b.title) === cible);
  if (exacte) return { id: exacte.id, title: exacte.title };
  if (prefill && compacte(prefill.title) === cible) return prefill;
  throw new ErreurAction(`Marque introuvable sur Vinted : « ${marque} ».`);
}

// Couleurs de la fiche (texte libre) → titre Vinted, quand la suggestion de Vinted manque.
const SYNONYMES_COULEUR: [string, string][] = [
  ["bleu marine", "Marine"],
  ["marine", "Marine"],
  ["bleu clair", "Bleu clair"],
  ["bleu ciel", "Bleu clair"],
  ["gris chine", "Gris"],
  ["anthracite", "Gris"],
  ["ecru", "Crème"],
  ["creme", "Crème"],
  ["lavande", "Lila"],
  ["mauve", "Lila"],
  ["lila", "Lila"],
  ["camel", "Camel"],
  ["kaki", "Kaki"],
  ["bordeaux", "Bordeaux"],
];

export function couleursDeLaFiche(couleur: string | null, liste: Couleur[]): number[] {
  const texte = ` ${normaliser(couleur)} `;
  if (!texte.trim()) return [];
  for (const [mot, titre] of SYNONYMES_COULEUR) {
    if (texte.includes(` ${mot} `)) {
      const c = liste.find((x) => normaliser(x.title) === normaliser(titre));
      if (c) return [c.id];
    }
  }
  const trouvees = liste
    .filter((c) => texte.includes(` ${normaliser(c.title)} `))
    .sort((a, b) => b.title.length - a.title.length);
  return trouvees.slice(0, 1).map((c) => c.id);
}

/** Couleur : suggestion de Vinted (d'après les photos), sinon correspondance avec la fiche. */
export function choisirCouleurs(couleur: string | null, suggestions: SuggestionsAttributs, liste: Couleur[]): number[] {
  const suggerees = suggestionsDe(suggestions, "color");
  if (suggerees.length) return suggerees.slice(0, 2);
  return couleursDeLaFiche(couleur, liste);
}

/** Matière : suggestion de Vinted, sinon mots de la composition de la fiche (« 80 % coton »). */
export function choisirMatieres(matiere: string | null, suggestions: SuggestionsAttributs, attributs: Attribut[]): number[] {
  const config = attribut(attributs, "material")?.configuration;
  if (!config) return [];
  const options = optionsAplaties(config.options);
  const limite = config.selection_limit ?? 3;
  const suggerees = suggestionsDe(suggestions, "material").filter((id) => options.some((o) => o.id === id));
  if (suggerees.length) return suggerees.slice(0, limite);
  const texte = ` ${normaliser(matiere)} `;
  return options
    .filter((o) => texte.includes(` ${normaliser(o.title)} `))
    .map((o) => o.id)
    .slice(0, limite);
}

function suggestionsDe(suggestions: SuggestionsAttributs, code: string): number[] {
  const attr = (suggestions.dynamic_attributes ?? []).find((a) => a.code === code);
  const ids = attr?.prefill_option_ids?.length ? attr.prefill_option_ids : (attr?.suggested_option_ids ?? []);
  return ids.map(Number).filter((n) => Number.isFinite(n));
}
