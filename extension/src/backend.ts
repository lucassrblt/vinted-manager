/** Client du backend vinted-manager, utilisé uniquement par le service worker. */
import type { Tache } from "./protocole";
import type { ChargeBrouillon } from "./vinted/brouillon";

export interface CompteBackend {
  compte_id: number;
  nom: string;
  vinted_user_id: number | null;
  pause: boolean;
  pause_raison: string | null;
  brouillons_du_jour: number;
  brouillons_max_jour: number;
  automatisation_active: boolean;
  heures_actives: boolean;
  heure_debut: number;
  heure_fin: number;
  modules: Record<string, boolean>;
}

export interface ResultatTache {
  ok: boolean;
  resultat?: Record<string, unknown> | null;
  erreur?: string;
  arret?: boolean;
  erreur_vinted?: boolean;
}

export class ErreurBackend extends Error {
  constructor(
    message: string,
    public readonly statut: number,
  ) {
    super(message);
    this.name = "ErreurBackend";
  }
}

export type FetchBackend = (url: string, init: RequestInit) => Promise<Response>;

export class ClientBackend {
  constructor(
    private readonly fetch: FetchBackend,
    private readonly url: string,
    private readonly jeton: string,
  ) {}

  private async requete(methode: string, chemin: string, corps?: unknown): Promise<Response> {
    let res: Response;
    try {
      res = await this.fetch(`${this.url.replace(/\/+$/, "")}/api/extension${chemin}`, {
        method: methode,
        headers: {
          "X-Extension-Token": this.jeton,
          ...(corps !== undefined ? { "Content-Type": "application/json" } : {}),
        },
        body: corps !== undefined ? JSON.stringify(corps) : undefined,
      });
    } catch {
      throw new ErreurBackend("vinted-manager injoignable : le backend est-il lancé ?", 0);
    }
    if (res.status === 401) throw new ErreurBackend("Jeton d'extension refusé : vérifie les options.", 401);
    if (!res.ok) {
      let detail = `Erreur ${res.status}`;
      try {
        const corpsErreur = (await res.json()) as { detail?: unknown };
        if (typeof corpsErreur.detail === "string") detail = corpsErreur.detail;
      } catch {
        /* corps non JSON */
      }
      throw new ErreurBackend(detail, res.status);
    }
    return res;
  }

  private async json<T>(methode: string, chemin: string, corps?: unknown): Promise<T | null> {
    const res = await this.requete(methode, chemin, corps);
    if (res.status === 204) return null;
    return (await res.json()) as T;
  }

  async compte(): Promise<CompteBackend> {
    return (await this.json<CompteBackend>("GET", "/compte"))!;
  }

  async heartbeat(
    vintedUserId: number | null,
    login: string | null,
    version: string,
    onglet: boolean,
  ): Promise<CompteBackend> {
    return (await this.json<CompteBackend>("POST", "/heartbeat", {
      vinted_user_id: vintedUserId,
      login,
      version,
      onglet,
    }))!;
  }

  tacheSuivante(): Promise<Tache | null> {
    return this.json<Tache>("GET", "/taches/suivante");
  }

  async resultatTache(id: number, r: ResultatTache): Promise<void> {
    await this.requete("POST", `/taches/${id}/resultat`, r);
  }

  /** Observation remontée au backend, qui décide ; sa réponse peut demander des lectures à faire. */
  async evenement<R = Record<string, unknown>>(type: string, donnees: Record<string, unknown>): Promise<R> {
    return (await this.json<R>("POST", "/evenements", { type, donnees }))!;
  }

  async arret(raison: string): Promise<CompteBackend> {
    return (await this.json<CompteBackend>("POST", "/arret", { raison }))!;
  }

  async pause(pause: boolean): Promise<CompteBackend> {
    return (await this.json<CompteBackend>("POST", pause ? "/pause" : "/reprendre"))!;
  }

  brouillonSuivant(): Promise<ChargeBrouillon | null> {
    return this.json<ChargeBrouillon>("GET", "/brouillons/suivant");
  }

  async resultatBrouillon(
    articleId: number,
    r: { ok: boolean; vinted_draft_id?: number; ai_photo?: boolean; erreur?: string; arret?: boolean },
  ): Promise<void> {
    await this.requete("POST", `/brouillons/${articleId}/resultat`, r);
  }

  async photo(photoId: number): Promise<ArrayBuffer> {
    return (await this.requete("GET", `/photos/${photoId}`)).arrayBuffer();
  }

  async photoTache(tacheId: number, index: number): Promise<ArrayBuffer> {
    return (await this.requete("GET", `/taches/${tacheId}/photos/${index}`)).arrayBuffer();
  }

  /** Photos d'une annonce importée, téléchargées depuis Vinted, gardées comme référence. */
  async photosReference(articleId: number, images: Blob[]): Promise<void> {
    const formulaire = new FormData();
    images.forEach((image, i) => formulaire.append("fichiers", image, `vinted-${i}.jpg`));
    let res: Response;
    try {
      res = await this.fetch(`${this.url.replace(/\/+$/, "")}/api/extension/articles/${articleId}/photos-reference`, {
        method: "POST",
        headers: { "X-Extension-Token": this.jeton },
        body: formulaire,
      });
    } catch {
      throw new ErreurBackend("vinted-manager injoignable : le backend est-il lancé ?", 0);
    }
    if (!res.ok) throw new ErreurBackend(`Photos de référence refusées (${res.status}).`, res.status);
  }
}
