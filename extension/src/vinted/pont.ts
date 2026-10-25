/**
 * Requêtes Vinted envoyées depuis le contexte de la page (voir src/pont.ts) : sérialisation de la
 * requête (un FormData ne traverse pas `postMessage`), exécution, et réponse rendue au content script.
 */
import type { Fetch } from "./client";

export const SOURCE_CONTENU = "vinted-manager:contenu";
export const SOURCE_PONT = "vinted-manager:pont";
export const DELAI_PONT_MS = 60_000;

type Champ = { nom: string; valeur: string } | { nom: string; fichier: Blob; nomFichier: string };

export interface RequetePont {
  url: string;
  method: string;
  headers: Record<string, string>;
  credentials: RequestCredentials;
  corps: string | null;
  formulaire: Champ[] | null;
}

export type ReponsePont = { ok: true; status: number; texte: string } | { ok: false; erreur: string };

export function serialiser(url: string, init: RequestInit): RequetePont {
  let formulaire: Champ[] | null = null;
  if (init.body instanceof FormData) {
    formulaire = [...init.body.entries()].map(([nom, v]) =>
      typeof v === "string" ? { nom, valeur: v } : { nom, fichier: v, nomFichier: v.name || "photo.jpg" },
    );
  }
  return {
    url,
    method: init.method ?? "GET",
    headers: (init.headers ?? {}) as Record<string, string>,
    credentials: init.credentials ?? "include",
    corps: typeof init.body === "string" ? init.body : null,
    formulaire,
  };
}

export async function executer(r: RequetePont, fetch: Fetch): Promise<ReponsePont> {
  // Seules les adresses de Vinted passent par le pont.
  if (!/^https:\/\/(www|api)\.vinted\.fr\//.test(r.url)) return { ok: false, erreur: `Adresse refusée : ${r.url}` };
  let body: BodyInit | undefined;
  if (r.formulaire) {
    const f = new FormData();
    for (const c of r.formulaire) {
      if ("fichier" in c) f.append(c.nom, c.fichier, c.nomFichier);
      else f.append(c.nom, c.valeur);
    }
    body = f;
  } else if (r.corps !== null) {
    body = r.corps;
  }
  try {
    const res = await fetch(r.url, { method: r.method, headers: r.headers, credentials: r.credentials, body });
    return { ok: true, status: res.status, texte: await res.text() };
  } catch (e) {
    return { ok: false, erreur: e instanceof Error ? e.message : String(e) };
  }
}

/** `fetch` du content script qui délègue au pont de la page. */
export function fetchParLaPage(
  envoyer: (message: unknown) => void,
  ecouter: (rappel: (donnees: unknown) => void) => () => void,
  delaiMs = DELAI_PONT_MS,
): Fetch {
  let compteur = 0;
  return (url, init) =>
    new Promise<Response>((resoudre, rejeter) => {
      compteur += 1;
      const id = `${Date.now().toString(36)}-${compteur}-${Math.random().toString(36).slice(2)}`;
      const minuterie = setTimeout(() => {
        arreter();
        rejeter(new TypeError("Le pont de la page Vinted ne répond pas."));
      }, delaiMs);
      const arreter = ecouter((donnees) => {
        const d = donnees as { source?: string; id?: string; reponse?: ReponsePont } | null;
        if (!d || d.source !== SOURCE_PONT || d.id !== id || !d.reponse) return;
        clearTimeout(minuterie);
        arreter();
        if (d.reponse.ok) resoudre(new Response(d.reponse.texte, { status: d.reponse.status }));
        else rejeter(new TypeError(d.reponse.erreur));
      });
      envoyer({ source: SOURCE_CONTENU, id, requete: serialiser(url, init) });
    });
}
