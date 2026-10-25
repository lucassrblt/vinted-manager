/**
 * Messages typés entre le service worker et le content script : `{type, id, payload}`.
 * Le service worker est le seul à parler au backend ; le content script, le seul à parler à Vinted.
 */
import type { ChargeBrouillon } from "./vinted/brouillon";

export interface MessageBase<T extends string, P> {
  type: T;
  id: string;
  payload: P;
}

// Service worker → content script
export type VersContenu =
  | MessageBase<"ping", null>
  | MessageBase<"compte", null>
  | MessageBase<"brouillon", { charge: ChargeBrouillon; vinted_user_id: number | null }>;

// Content script → service worker
export type VersFond = MessageBase<"photo", { photo_id: number }>;

export type Reponse<R = unknown> =
  | { ok: true; resultat: R }
  | { ok: false; erreur: string; arret: boolean; mauvais_compte: boolean };

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
