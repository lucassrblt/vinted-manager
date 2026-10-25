/**
 * Logique du service worker, sans dépendre directement de l'API Chrome (testable).
 *
 * À chaque réveil (alarme de 30 s) : signal de vie au backend (chaque minute), puis au plus une
 * action, demandée au backend. Le backend décide de tout ; ici, on exécute et on rend compte.
 */
import { type ClientBackend, type CompteBackend, ErreurBackend } from "./backend";
import type { Etat } from "./etat";
import { entre } from "./outils";
import { nouvelId, type Reponse, type ResultatCompte, type VersContenu } from "./protocole";

export const PERIODE_HEARTBEAT_MS = 60_000;
export const INTERVALLE_BROUILLON_MS = 5 * 60_000;
export const ALEA_BROUILLON_MS = 120_000;
// Au-delà, une action « en cours » est considérée comme perdue (service worker redémarré).
export const OCCUPATION_MAX_MS = 10 * 60_000;

export interface Memoire {
  prochainBrouillon: number;
  dernierHeartbeat: number;
  occupeDepuis: number | null;
}

export const MEMOIRE_INITIALE: Memoire = { prochainBrouillon: 0, dernierHeartbeat: 0, occupeDepuis: null };

export interface Environnement {
  backend: ClientBackend | null;
  ongletVinted(): Promise<number | null>;
  envoyer<R>(onglet: number, message: VersContenu): Promise<Reponse<R>>;
  maintenant(): number;
  aleatoire(): number;
  lireMemoire(): Promise<Memoire>;
  ecrireMemoire(m: Memoire): Promise<void>;
  majEtat(partiel: Partial<Etat>): Promise<void>;
  version: string;
}

export class Moteur {
  constructor(private readonly env: Environnement) {}

  async tick(): Promise<void> {
    const { env } = this;
    if (!env.backend) {
      await env.majEtat({ statut: "non_configure", message: "Renseigne l'URL du backend et le jeton dans les options." });
      return;
    }
    const memoire = await env.lireMemoire();
    try {
      await this.cycle(env.backend, memoire);
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      await env.majEtat({ statut: "erreur", message });
    } finally {
      await env.ecrireMemoire(memoire);
    }
  }

  private async cycle(backend: ClientBackend, memoire: Memoire): Promise<void> {
    const { env } = this;
    const onglet = await env.ongletVinted();
    let compte: CompteBackend | null = null;
    if (env.maintenant() - memoire.dernierHeartbeat >= PERIODE_HEARTBEAT_MS) {
      compte = await this.heartbeat(backend, onglet);
      memoire.dernierHeartbeat = env.maintenant();
    }
    if (onglet === null) {
      await env.majEtat({ statut: "onglet_ferme", message: "Ouvre un onglet www.vinted.fr dans ce profil." });
      return;
    }
    if (memoire.occupeDepuis !== null && env.maintenant() - memoire.occupeDepuis < OCCUPATION_MAX_MS) return;
    memoire.occupeDepuis = null;
    compte ??= await backend.compte();
    await this.afficherCompte(compte);
    if (compte.pause) return;
    if (env.maintenant() >= memoire.prochainBrouillon) {
      memoire.prochainBrouillon = env.maintenant() + INTERVALLE_BROUILLON_MS + entre(0, ALEA_BROUILLON_MS, env.aleatoire);
      memoire.occupeDepuis = env.maintenant();
      await env.ecrireMemoire(memoire);
      try {
        await this.brouillon(backend, onglet, compte);
      } finally {
        memoire.occupeDepuis = null;
      }
    }
  }

  private async afficherCompte(compte: CompteBackend): Promise<void> {
    await this.env.majEtat({
      statut: compte.pause ? "pause" : "actif",
      message: compte.pause ? compte.pause_raison : null,
      compte_nom: compte.nom,
      brouillons_du_jour: compte.brouillons_du_jour,
      brouillons_max_jour: compte.brouillons_max_jour,
    });
  }

  /** Signal de vie, avec le compte Vinted connecté dans l'onglet (contrôle fait par le backend). */
  private async heartbeat(backend: ClientBackend, onglet: number | null): Promise<CompteBackend> {
    let vu: ResultatCompte | null = null;
    let arret: string | null = null;
    if (onglet !== null) {
      const r = await this.env.envoyer<ResultatCompte>(onglet, { type: "compte", id: nouvelId(), payload: null });
      if (r.ok) vu = r.resultat;
      else if (r.arret) arret = r.erreur;
    }
    let compte = await backend.heartbeat(vu?.id ?? null, vu?.login ?? null, this.env.version);
    // Session expirée, captcha… : arrêt du compte (une seule fois, la reprise est manuelle).
    if (arret && !compte.pause) compte = await backend.arret(arret);
    await this.env.majEtat({ vinted_login: vu?.login ?? null, vinted_user_id: vu?.id ?? null });
    return compte;
  }

  private async brouillon(backend: ClientBackend, onglet: number, compte: CompteBackend): Promise<void> {
    const charge = await backend.brouillonSuivant();
    if (!charge) return;
    const r = await this.env.envoyer<{ vinted_draft_id: number; ai_photo: boolean }>(onglet, {
      type: "brouillon",
      id: nouvelId(),
      payload: { charge, vinted_user_id: compte.vinted_user_id },
    });
    if (r.ok) {
      await backend.resultatBrouillon(charge.article_id, {
        ok: true,
        vinted_draft_id: r.resultat.vinted_draft_id,
        ai_photo: r.resultat.ai_photo,
      });
      await this.action(`Brouillon créé : ${charge.titre}`);
    } else {
      await backend.resultatBrouillon(charge.article_id, { ok: false, erreur: r.erreur, arret: r.arret });
      await this.action(`Brouillon en erreur : ${r.erreur}`);
    }
  }

  private async action(texte: string): Promise<void> {
    await this.env.majEtat({ derniere_action: { date: this.env.maintenant(), texte } });
  }
}

/** Erreur de l'onglet (content script absent, page en rechargement) : jamais d'arrêt du compte. */
export function reponseIndisponible(message: string): Reponse<never> {
  return { ok: false, erreur: message, arret: false, mauvais_compte: false };
}

export { ErreurBackend };
