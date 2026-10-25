/**
 * Faux Vinted pour les tests : répond avec les captures réelles anonymisées de tests/fixtures/vinted/.
 * Aucun appel réseau : toute requête non prévue fait échouer le test.
 */
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

import type { Fetch } from "../src/vinted/client";

const DOSSIER = join(__dirname, "fixtures", "vinted");

export interface Capture {
  request: { method: string; url: string; query?: string; json?: unknown };
  response: { status: number; body: unknown };
}

export function capture(nom: string): Capture {
  return JSON.parse(readFileSync(join(DOSSIER, `${nom}.json`), "utf-8")) as Capture;
}

export function toutesLesCaptures(): string[] {
  return readdirSync(DOSSIER)
    .filter((f) => f.endsWith(".json"))
    .map((f) => f.replace(/\.json$/, ""));
}

export interface Reponse {
  status?: number;
  body?: unknown;
  texte?: string;
}

export interface Appel {
  methode: string;
  url: string;
  entetes: Record<string, string>;
  corps: unknown;
  credentials: RequestCredentials | undefined;
}

type Gestionnaire = (url: string, corps: unknown) => Reponse;

// Compte de test des captures (le dressing capturé est celui de l'utilisateur 3201823662).
export const UTILISATEUR = { user: { id: 3201823662, login: "jeanmekloul" } };

export class FauxVinted {
  appels: Appel[] = [];
  private routes: { methode: string; motif: RegExp; gestionnaire: Gestionnaire }[] = [];

  constructor() {
    const r = (nom: string): Reponse => ({ status: 200, body: capture(nom).response.body });
    this.sur("GET", /^https:\/\/www\.vinted\.fr\/api\/v2\/users\/current$/, () => ({ body: UTILISATEUR }));
    this.sur("POST", /\/api\/v2\/photos$/, () => r("photos_upload"));
    this.sur("POST", /\/item_upload\/suggestions\/categories$/, () => r("suggestions_categories"));
    this.sur("POST", /\/item_upload\/attributes$/, (_u, corps) => {
      const id = (corps as { attributes: { value: number[] }[] }).attributes[0]?.value[0];
      return r(id === 268 ? "attributes_268" : "attributes_1806");
    });
    this.sur("POST", /\/item_upload\/suggestions\/attributes$/, () => r("suggestions_attributes"));
    this.sur("GET", /\/item_upload\/brands\?category_id=\d+$/, () => r("brands_1806"));
    this.sur("GET", /\/item_upload\/colors$/, () => r("colors"));
    this.sur("POST", /\/item_upload\/drafts$/, () => r("drafts_create"));
    this.sur("POST", /\/item_upload\/drafts\/\d+\/completion$/, () => r("drafts_completion"));
    this.sur("PUT", /\/item_upload\/items\/\d+$/, () => r("items_update"));
    this.sur("POST", /\/api\/v2\/items\/\d+\/delete$/, () => r("items_delete"));
    this.sur("GET", /\/api\/v2\/wardrobe\/\d+\/items\?page=\d+&per_page=\d+$/, () => r("wardrobe_items"));
    this.sur("GET", /\/offers\/seller_options$/, () => r("offers_seller_options"));
    this.sur("POST", /\/api\/v2\/transactions\/\d+\/offers$/, () => r("offers_counter"));
    this.sur("PUT", /\/offer_requests\/\d+\/accept$/, () => r("offer_request_accept"));
    this.sur("PUT", /\/offer_requests\/\d+\/reject$/, () => r("offer_request_reject"));
    this.sur("GET", /^https:\/\/api\.vinted\.fr\/messaging\/main\/inbox$/, () => r("messaging_inbox"));
    this.sur("GET", /^https:\/\/api\.vinted\.fr\/messaging\/main\/conversations\/[\w-]+$/, () => r("messaging_conversation"));
    this.sur("POST", /\/messaging\/main\/conversations\/[\w-]+\/replies$/, () => ({
      status: 201,
      body: capture("messaging_reply").response.body,
    }));
    this.sur("GET", /\/messaging\/main\/users\/unread_count$/, () => r("messaging_unread_count"));
    this.sur("GET", /\/inbox-notifications\/v1\/notifications\/unread_count$/, () => r("notifications_unread_count"));
  }

  /** Ajoute (ou remplace, la dernière déclarée gagne) une route. */
  sur(methode: string, motif: RegExp, gestionnaire: Gestionnaire): this {
    this.routes.unshift({ methode, motif, gestionnaire });
    return this;
  }

  fetch: Fetch = async (url, init) => {
    const methode = (init.method ?? "GET").toUpperCase();
    let corps: unknown = null;
    if (typeof init.body === "string") corps = JSON.parse(init.body);
    else if (init.body instanceof FormData) corps = Object.fromEntries([...init.body.entries()].map(([k, v]) => [k, typeof v === "string" ? v : "<fichier>"]));
    this.appels.push({ methode, url, entetes: (init.headers ?? {}) as Record<string, string>, corps, credentials: init.credentials });
    const route = this.routes.find((r) => r.methode === methode && r.motif.test(url));
    if (!route) throw new Error(`Requête non prévue dans le faux Vinted : ${methode} ${url}`);
    const rep = route.gestionnaire(url, corps);
    const texte = rep.texte ?? JSON.stringify(rep.body ?? {});
    return new Response(texte, { status: rep.status ?? 200, headers: { "content-type": "application/json" } });
  };

  ecritures(): Appel[] {
    return this.appels.filter((a) => a.methode !== "GET");
  }
}
