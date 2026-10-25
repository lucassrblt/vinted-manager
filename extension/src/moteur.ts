/**
 * Logique du service worker, sans dépendre directement de l'API Chrome (testable).
 *
 * À chaque réveil (alarme de 30 s) : signal de vie au backend (chaque minute), puis au plus une
 * tâche de la file du backend. Le backend décide de tout (priorités, heures, budget, délais) ; ici,
 * on exécute et on rend compte, sans jamais réessayer une action qui a échoué.
 */
import type { ClientBackend, CompteBackend } from "./backend";
import type { Etat } from "./etat";
import { type Attendre, entre } from "./outils";
import { type Compteurs, nouvelId, type Reponse, type ResultatCompte, type VersContenu } from "./protocole";

export const PERIODE_HEARTBEAT_MS = 60_000;
// Au-delà, une action « en cours » est considérée comme perdue (service worker redémarré).
export const OCCUPATION_MAX_MS = 10 * 60_000;
// Dressing relu toutes les 30 min (et au démarrage) ; messagerie relue au moins toutes les 5 min.
export const PERIODE_DRESSING_MS = 30 * 60_000;
export const PERIODE_INBOX_MS = 5 * 60_000;
export const CONVERSATIONS_MAX = 5;

export interface Memoire {
  dernierHeartbeat: number;
  occupeDepuis: number | null;
  dernierDressing: number;
  derniereInbox: number;
  inboxDemandee: boolean;
}

export const MEMOIRE_INITIALE: Memoire = {
  dernierHeartbeat: 0,
  occupeDepuis: null,
  dernierDressing: 0,
  derniereInbox: 0,
  inboxDemandee: false,
};

export interface Environnement {
  backend: ClientBackend | null;
  ongletVinted(): Promise<number | null>;
  envoyer<R>(onglet: number, message: VersContenu): Promise<Reponse<R>>;
  maintenant(): number;
  attendre: Attendre;
  aleatoire(): number;
  lireMemoire(): Promise<Memoire>;
  ecrireMemoire(m: Memoire): Promise<void>;
  majEtat(partiel: Partial<Etat>): Promise<void>;
  version: string;
}

const LIBELLES: Record<string, string> = {
  brouillon: "Brouillon",
  repondre_message: "Réponse",
  accepter_offre: "Offre acceptée",
  refuser_offre: "Offre refusée",
  contre_offre: "Contre-offre",
  relance_favori: "Relance d'un favori",
  republication: "Republication",
  modifier_prix: "Baisse de prix",
  message_apres_vente: "Message après-vente",
  photos_reference: "Photos de référence",
};

export class Moteur {
  constructor(private readonly env: Environnement) {}

  async tick(): Promise<void> {
    const { env } = this;
    if (!env.backend) {
      await env.majEtat({
        statut: "non_configure",
        message: "Renseigne l'URL du backend et le jeton dans les options.",
      });
      return;
    }
    const memoire = { ...MEMOIRE_INITIALE, ...(await env.lireMemoire()) };
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
    if (compte.pause || !compte.automatisation_active) return;
    // L'onglet relève les compteurs de non-lus tant qu'il reçoit cette consigne (toutes les 30 s).
    await env.envoyer(onglet, {
      type: "surveillance",
      id: nouvelId(),
      payload: { actif: true, nuit: !compte.heures_actives },
    });
    if (env.maintenant() - memoire.dernierDressing >= PERIODE_DRESSING_MS) {
      memoire.dernierDressing = env.maintenant();
      await this.lireDressing(backend, onglet, compte);
      return; // une lecture lourde par réveil
    }
    if (
      compte.modules.assistant !== false &&
      (memoire.inboxDemandee || env.maintenant() - memoire.derniereInbox >= PERIODE_INBOX_MS)
    ) {
      memoire.inboxDemandee = false;
      memoire.derniereInbox = env.maintenant();
      if (!(await this.lireMessagerie(backend, onglet, compte))) return;
    }
    const tache = await backend.tacheSuivante();
    if (!tache) return;
    memoire.occupeDepuis = env.maintenant();
    await env.ecrireMemoire(memoire);
    try {
      const r = await env.envoyer<Record<string, unknown>>(onglet, {
        type: "executer",
        id: nouvelId(),
        payload: { tache, vinted_user_id: compte.vinted_user_id },
      });
      const libelle = LIBELLES[tache.type] ?? tache.type;
      if (r.ok) {
        await backend.resultatTache(tache.id, { ok: true, resultat: r.resultat });
        await this.action(`${libelle} : fait`);
      } else {
        await backend.resultatTache(tache.id, {
          ok: false,
          erreur: r.erreur,
          arret: r.arret,
          erreur_vinted: r.erreur_vinted ?? false,
        });
        await this.action(`${libelle} : ${r.erreur}`);
      }
    } finally {
      memoire.occupeDepuis = null;
    }
  }

  /** Compteurs de non-lus en hausse (ou erreur) signalés par l'onglet. */
  async compteurs(c: Compteurs): Promise<void> {
    const memoire = { ...MEMOIRE_INITIALE, ...(await this.env.lireMemoire()) };
    memoire.inboxDemandee = true;
    await this.env.ecrireMemoire(memoire);
    if (c.arret && c.erreur && this.env.backend) {
      const compte = await this.env.backend.compte();
      if (!compte.pause) await this.env.backend.arret(c.erreur);
    }
  }

  /** Réponse d'une lecture : en cas d'échec inattendu (401, 403…), arrêt du compte. */
  private async lecture<R>(
    backend: ClientBackend,
    compte: CompteBackend,
    onglet: number,
    message: VersContenu,
  ): Promise<R | null> {
    const r = await this.env.envoyer<R>(onglet, message);
    if (r.ok) return r.resultat;
    if (r.arret && !compte.pause) await backend.arret(r.erreur);
    await this.action(`Lecture impossible : ${r.erreur}`);
    return null;
  }

  private async lireDressing(backend: ClientBackend, onglet: number, compte: CompteBackend): Promise<void> {
    const r = await this.lecture<Record<string, unknown>>(backend, compte, onglet, {
      type: "dressing",
      id: nouvelId(),
      payload: { user_id: compte.vinted_user_id },
    });
    if (r) await backend.evenement("dressing", r);
  }

  /** Inbox → le backend dit quelles conversations lire → chacune lui est transmise. Faux si arrêt. */
  private async lireMessagerie(backend: ClientBackend, onglet: number, compte: CompteBackend): Promise<boolean> {
    const inbox = await this.lecture<Record<string, unknown>>(backend, compte, onglet, {
      type: "inbox",
      id: nouvelId(),
      payload: null,
    });
    if (!inbox) return false;
    const { a_lire } = await backend.evenement<{ a_lire?: string[] }>("inbox", inbox);
    for (const id of (a_lire ?? []).slice(0, CONVERSATIONS_MAX)) {
      await this.env.attendre(entre(2000, 4000, this.env.aleatoire));
      const conversation = await this.lecture<Record<string, unknown>>(backend, compte, onglet, {
        type: "conversation",
        id: nouvelId(),
        payload: { id },
      });
      if (!conversation) return false;
      await backend.evenement("conversation", conversation);
    }
    return true;
  }

  private async afficherCompte(compte: CompteBackend): Promise<void> {
    const pause = compte.pause || !compte.automatisation_active;
    await this.env.majEtat({
      statut: pause ? "pause" : "actif",
      message: compte.pause
        ? compte.pause_raison
        : compte.automatisation_active
          ? null
          : "Automatisation coupée dans vinted-manager.",
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
    let compte = await backend.heartbeat(vu?.id ?? null, vu?.login ?? null, this.env.version, onglet !== null);
    // Session expirée, captcha… : arrêt du compte (une seule fois, la reprise est manuelle).
    if (arret && !compte.pause) compte = await backend.arret(arret);
    await this.env.majEtat({ vinted_login: vu?.login ?? null, vinted_user_id: vu?.id ?? null });
    return compte;
  }

  private async action(texte: string): Promise<void> {
    await this.env.majEtat({ derniere_action: { date: this.env.maintenant(), texte } });
  }
}

/** Erreur de l'onglet (content script absent, page en rechargement) : jamais d'arrêt du compte. */
export function reponseIndisponible(message: string): Reponse<never> {
  return { ok: false, erreur: message, arret: false, mauvais_compte: false, erreur_vinted: false };
}
