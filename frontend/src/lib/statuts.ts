import type { Etat, Statut, StatutEnvoi, TypeEmail } from "@/lib/types";

// Une seule définition des libellés et couleurs de statut, utilisée dans toute l'app.
export const STATUTS: Record<Statut, { libelle: string; classe: string; point: string }> = {
  commande: {
    libelle: "Commandé",
    classe: "bg-zinc-100 text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300",
    point: "bg-zinc-400",
  },
  recu_a_publier: {
    libelle: "Reçu · à publier",
    classe: "bg-amber-50 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
    point: "bg-amber-500",
  },
  en_ligne: {
    libelle: "En ligne",
    classe: "bg-sky-50 text-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
    point: "bg-sky-500",
  },
  vendu: {
    libelle: "Vendu",
    classe: "bg-brand-soft text-brand dark:text-brand",
    point: "bg-brand",
  },
  envoye: {
    libelle: "Envoyé",
    classe: "bg-violet-50 text-violet-800 dark:bg-violet-950/60 dark:text-violet-300",
    point: "bg-violet-500",
  },
  livre: {
    libelle: "Livré",
    classe: "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300",
    point: "bg-emerald-600",
  },
  litige: {
    libelle: "Litige",
    classe: "bg-red-50 text-red-700 dark:bg-red-950/60 dark:text-red-300",
    point: "bg-red-500",
  },
  retourne: {
    libelle: "Retourné",
    classe: "bg-orange-50 text-orange-800 dark:bg-orange-950/60 dark:text-orange-300",
    point: "bg-orange-500",
  },
};

export const ORDRE_STATUTS: Statut[] = [
  "commande",
  "recu_a_publier",
  "en_ligne",
  "vendu",
  "envoye",
  "livre",
  "litige",
  "retourne",
];

export const INDICATEURS: Record<string, string> = {
  "Sous l'objectif": "bg-red-50 text-red-700 dark:bg-red-950/60 dark:text-red-300",
  OK: "bg-brand-soft text-brand",
  "Au-dessus": "bg-sky-50 text-sky-800 dark:bg-sky-950/60 dark:text-sky-300",
};

export const ETATS: Record<Etat, string> = {
  neuf_avec_etiquette: "Neuf avec étiquette",
  neuf_sans_etiquette: "Neuf sans étiquette",
  tres_bon_etat: "Très bon état",
  bon_etat: "Bon état",
  satisfaisant: "Satisfaisant",
};

export const TYPES_PREUVE: Record<string, string> = {
  facture: "Facture",
  capture_commande: "Capture de commande",
  photo_etiquette: "Photo d'étiquette",
  certificat: "Certificat",
  autre: "Autre",
};

export const TYPES_EMAIL: Record<TypeEmail, string> = {
  vente: "Vente",
  bordereau: "Bordereau",
  message: "Message reçu",
  offre: "Offre reçue",
  favori: "Mis en favori",
  expedie: "Colis expédié",
  livre: "Colis livré",
  argent_disponible: "Argent disponible",
  evaluation: "Évaluation reçue",
  litige: "Litige",
  annulation: "Commande annulée",
  autre: "Autre",
};

export const STATUTS_ENVOI: Record<StatutEnvoi, { libelle: string; classe: string }> = {
  a_imprimer: { libelle: "À imprimer", classe: "bg-amber-50 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300" },
  imprime: { libelle: "Imprimé", classe: "bg-sky-50 text-sky-800 dark:bg-sky-950/60 dark:text-sky-300" },
  depose: { libelle: "Déposé", classe: "bg-violet-50 text-violet-800 dark:bg-violet-950/60 dark:text-violet-300" },
  livre: { libelle: "Livré", classe: "bg-emerald-50 text-emerald-800 dark:bg-emerald-950/60 dark:text-emerald-300" },
};

export const ORDRE_ENVOI: StatutEnvoi[] = ["a_imprimer", "imprime", "depose", "livre"];
