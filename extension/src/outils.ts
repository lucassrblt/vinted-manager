/** Petits outils communs : attente, tirage aléatoire, UUID. */

export type Attendre = (ms: number) => Promise<void>;

export const attendre: Attendre = (ms) => new Promise((r) => setTimeout(r, ms));

/** Entier aléatoire entre `min` et `max` inclus (millisecondes en général). */
export function entre(min: number, max: number, aleatoire: () => number = Math.random): number {
  return Math.round(min + (max - min) * aleatoire());
}

export function uuid(): string {
  return crypto.randomUUID();
}

export function normaliser(texte: string | null | undefined): string {
  return (texte ?? "")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .trim();
}

export function base64VersBlob(base64: string, type = "image/jpeg"): Blob {
  const binaire = atob(base64);
  const octets = new Uint8Array(binaire.length);
  for (let i = 0; i < binaire.length; i++) octets[i] = binaire.charCodeAt(i);
  return new Blob([octets], { type });
}

export function blobVersBase64(octets: ArrayBuffer): string {
  const vue = new Uint8Array(octets);
  let binaire = "";
  for (let i = 0; i < vue.length; i += 0x8000) binaire += String.fromCharCode(...vue.subarray(i, i + 0x8000));
  return btoa(binaire);
}
