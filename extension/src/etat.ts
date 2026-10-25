/** État affiché dans la popup (chrome.storage.local) : le minimum, le reste est dans vinted-manager. */

export type Statut = "non_configure" | "actif" | "pause" | "erreur" | "onglet_ferme";

export interface Etat {
  statut: Statut;
  message: string | null;
  compte_nom: string | null;
  vinted_login: string | null;
  vinted_user_id: number | null;
  brouillons_du_jour: number;
  brouillons_max_jour: number;
  derniere_action: { date: number; texte: string } | null;
}

export const ETAT_INITIAL: Etat = {
  statut: "non_configure",
  message: null,
  compte_nom: null,
  vinted_login: null,
  vinted_user_id: null,
  brouillons_du_jour: 0,
  brouillons_max_jour: 6,
  derniere_action: null,
};

export interface Config {
  backendUrl: string;
  jeton: string;
}

export const BACKEND_DEFAUT = "http://localhost:8000";
