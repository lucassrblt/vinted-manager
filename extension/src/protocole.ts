/**
 * Messages typés entre le service worker et le content script : `{type, id, payload}`.
 * Le service worker est le seul à parler au backend ; le content script, le seul à parler à Vinted.
 */

export interface MessageBase<T extends string, P> {
  type: T;
  id: string;
  payload: P;
}

/** Tâche de la file du backend (`GET /api/extension/taches/suivante`). */
export interface Tache {
  id: number;
  type: string;
  article_id: number | null;
  payload: Record<string, unknown>;
}

// Service worker → content script
export type VersContenu =
  | MessageBase<"ping", null>
  | MessageBase<"compte", null>
  | MessageBase<"inbox", null>
  | MessageBase<"conversation", { id: string }>
  | MessageBase<"dressing", { user_id: number | null }>
  | MessageBase<"notifications", { source: "api" | "www" | null }>
  | MessageBase<"verifier_compte", { vinted_user_id: number | null }>
  | MessageBase<"relance", { conversation_id: string; texte: string; montant: string; vinted_user_id: number | null }>
  | MessageBase<"surveillance", { actif: boolean; nuit: boolean }>
  | MessageBase<"executer", { tache: Tache; vinted_user_id: number | null }>;

/** Compteurs de non-lus relevés par l'onglet. */
export interface Compteurs {
  messages: number | null;
  notifications: number | null;
  erreur?: string;
  arret?: boolean;
}

// Content script → service worker
/** Photo d'un brouillon (`photo_id`) ou photo transformée d'une republication (`tache_id`, `index`). */
export type RefPhoto = { photo_id: number } | { tache_id: number; index: number };

export type VersFond = MessageBase<"photo", RefPhoto> | MessageBase<"compteurs", Compteurs>;

export interface Echec {
  ok: false;
  erreur: string;
  /** Réponse inattendue de Vinted (401, 403, 429, captcha, non JSON) : arrêt du compte. */
  arret: boolean;
  mauvais_compte: boolean;
  /** Refus renvoyé par Vinted (et non un contrôle de l'extension) : compte pour les erreurs consécutives. */
  erreur_vinted?: boolean;
  /** Ce qui a quand même été fait sur Vinted avant l'échec (ex. nouvelle annonce publiée). */
  resultat?: Record<string, unknown>;
}

export type Reponse<R = unknown> = { ok: true; resultat: R } | Echec;

export interface ResultatCompte {
  id: number;
  login: string | null;
}

export interface PhotoBase64 {
  base64: string;
}

let compteur = 0;
export function nouvelId(): string {
  compteur += 1;
  return `${Date.now().toString(36)}-${compteur}`;
}
