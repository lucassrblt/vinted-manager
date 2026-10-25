/** Faux backend vinted-manager : enregistre les appels, répond selon des gestionnaires simples. */
import { ClientBackend } from "../src/backend";

export interface AppelBackend {
  methode: string;
  chemin: string;
  corps: unknown;
  jeton: string | null;
}

type Gestionnaire = (corps: unknown) => { status?: number; body?: unknown; octets?: ArrayBuffer };

import type { CompteBackend } from "../src/backend";

export const COMPTE: CompteBackend = {
  compte_id: 1,
  nom: "Lucas",
  vinted_user_id: 3201823662,
  pause: false,
  pause_raison: null,
  brouillons_du_jour: 0,
  brouillons_max_jour: 6,
  automatisation_active: true,
  heures_actives: true,
  heure_debut: 8,
  heure_fin: 23,
  modules: { brouillons: true, assistant: true, favoris: true, republication: true, prix: true, apres_vente: true },
};

export class FauxBackend {
  appels: AppelBackend[] = [];
  routes = new Map<string, Gestionnaire>();
  compte: CompteBackend = { ...COMPTE };
  aLire: string[] = [];

  constructor() {
    this.sur("GET /compte", () => ({ body: this.compte }));
    this.sur("POST /heartbeat", () => ({ body: this.compte }));
    this.sur("POST /arret", (c) => {
      this.compte = { ...this.compte, pause: true, pause_raison: (c as { raison: string }).raison };
      return { body: this.compte };
    });
    this.sur("POST /pause", () => ({ body: (this.compte = { ...this.compte, pause: true }) }));
    this.sur("POST /reprendre", () => ({ body: (this.compte = { ...this.compte, pause: false }) }));
    this.sur("GET /brouillons/suivant", () => ({ status: 204 }));
    this.sur("GET /taches/suivante", () => ({ status: 204 }));
    this.sur("POST /taches/{n}/resultat", () => ({ status: 204 }));
    this.sur("POST /evenements", (c) => ({
      body: (c as { type: string }).type === "inbox" ? { a_lire: this.aLire } : { ok: true },
    }));
  }

  sur(cle: string, g: Gestionnaire): this {
    this.routes.set(cle, g);
    return this;
  }

  fetch = async (url: string, init: RequestInit): Promise<Response> => {
    const chemin = url.replace("http://localhost:8000/api/extension", "");
    const methode = init.method ?? "GET";
    const corps = typeof init.body === "string" ? JSON.parse(init.body) : null;
    const jeton = (init.headers as Record<string, string>)["X-Extension-Token"] ?? null;
    this.appels.push({ methode, chemin, corps, jeton });
    const g =
      this.routes.get(`${methode} ${chemin}`) ??
      [...this.routes.entries()].find(([k]) =>
        new RegExp(`^${k.replace(/\{n\}/g, "\\d+")}$`).test(`${methode} ${chemin}`),
      )?.[1];
    if (!g) return new Response(JSON.stringify({ detail: "inconnu" }), { status: 404 });
    const r = g(corps);
    if (r.status === 204) return new Response(null, { status: 204 });
    if (r.octets) return new Response(r.octets, { status: 200, headers: { "content-type": "image/jpeg" } });
    return new Response(JSON.stringify(r.body ?? {}), { status: r.status ?? 200 });
  };

  client(): ClientBackend {
    return new ClientBackend(this.fetch, "http://localhost:8000", "vmx_test");
  }

  chemins(): string[] {
    return this.appels.map((a) => `${a.methode} ${a.chemin}`);
  }
}
