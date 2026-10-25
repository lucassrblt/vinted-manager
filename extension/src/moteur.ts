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
import { type Compteurs, nouvelId, type Reponse, type ResultatCompte, type Tache, type VersContenu } from "./protocole";
import { conversationDepuisUrl, urlBloquante } from "./vinted/favoris";

export const PERIODE_HEARTBEAT_MS = 60_000;
// Au-delà, une action « en cours » est considérée comme perdue (service worker redémarré).
export const OCCUPATION_MAX_MS = 10 * 60_000;
// Dressing relu toutes les 30 min (et au démarrage) ; messagerie relue au moins toutes les 5 min.
export const PERIODE_DRESSING_MS = 30 * 60_000;
export const PERIODE_INBOX_MS = 5 * 60_000;
export const CONVERSATIONS_MAX = 5;

export const PERIODE_NOTIFICATIONS_MS = 5 * 60_000;
// La page « want_it » doit rediriger vers la conversation dans ce délai.
export const DELAI_WANT_IT_MS = 15_000;

export interface Memoire {
  dernierHeartbeat: number;
  occupeDepuis: number | null;
  dernierDressing: number;
  derniereInbox: number;
  inboxDemandee: boolean;
  dernieresNotifications: number;
  notificationsDemandees: boolean;
  sourceNotifications: "api" | "www" | null;
}

export const MEMOIRE_INITIALE: Memoire = {
  dernierHeartbeat: 0,
  occupeDepuis: null,
  dernierDressing: 0,
  derniereInbox: 0,
  inboxDemandee: false,
  dernieresNotifications: 0,
  notificationsDemandees: false,
  sourceNotifications: null,
};

/** Onglet de travail ouvert par l'extension, en arrière-plan (pages qui demandent une navigation). */
export interface OngletTravail {
  /** Navigue et attend une URL qui satisfait `attendue` ; renvoie l'URL finale, ou null après `delaiMs`. */
  naviguer(url: string, attendue: (url: string) => boolean, delaiMs: number): Promise<string | null>;
}

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
  ongletTravail: OngletTravail;
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
    if (
      compte.modules.favoris !== false &&
      (memoire.notificationsDemandees || env.maintenant() - memoire.dernieresNotifications >= PERIODE_NOTIFICATIONS_MS)
    ) {
      memoire.notificationsDemandees = false;
      memoire.dernieresNotifications = env.maintenant();
      const r = await this.lecture<{ source: "api" | "www"; notifications: unknown[] }>(backend, compte, onglet, {
        type: "notifications",
        id: nouvelId(),
        payload: { source: memoire.sourceNotifications },
      });
      if (!r) return;
      memoire.sourceNotifications = r.source;
      await backend.evenement("notifications", r as unknown as Record<string, unknown>);
    }
    const tache = await backend.tacheSuivante();
    if (!tache) return;
    memoire.occupeDepuis = env.maintenant();
    await env.ecrireMemoire(memoire);
    try {
      const r =
        tache.type === "relance_favori"
          ? await this.relanceFavori(onglet, tache, compte)
          : await env.envoyer<Record<string, unknown>>(onglet, {
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

  /**
   * Relance d'un favori : contrôle du compte, page « want_it » dans l'onglet de travail (elle ouvre ou
   * crée la conversation et redirige vers /inbox/{id}), message et offre depuis l'onglet principal,
   * puis l'onglet de travail revient sur le dressing.
   */
  private async relanceFavori(
    onglet: number,
    tache: Tache,
    compte: CompteBackend,
  ): Promise<Reponse<Record<string, unknown>>> {
    const p = tache.payload as { item_id: number; membre_id: number; texte: string; montant: string };
    const controle = await this.env.envoyer(onglet, {
      type: "verifier_compte",
      id: nouvelId(),
      payload: { vinted_user_id: compte.vinted_user_id },
    });
    if (!controle.ok) return controle;
    const url = `https://www.vinted.fr/inbox/want_it?receiver_id=${p.membre_id}&item_id=${p.item_id}`;
    const fin = await this.env.ongletTravail.naviguer(
      url,
      (u) => conversationDepuisUrl(u) !== null || urlBloquante(u),
      DELAI_WANT_IT_MS,
    );
    try {
      if (fin === null) {
        return echec("Conversation non ouverte par la page want_it en 15 s : rien n'a été envoyé.");
      }
      if (urlBloquante(fin)) {
        return echec(`Vinted a redirigé vers ${fin} (session expirée ou vérification) : arrêt.`, true);
      }
      const conversation = conversationDepuisUrl(fin) as string;
      return await this.env.envoyer<Record<string, unknown>>(onglet, {
        type: "relance",
        id: nouvelId(),
        payload: {
          conversation_id: conversation,
          texte: p.texte,
          montant: p.montant,
          vinted_user_id: compte.vinted_user_id,
        },
      });
    } finally {
      await this.env.ongletTravail.naviguer(`https://www.vinted.fr/member/${compte.vinted_user_id}`, () => true, 5_000);
    }
  }

  /** Compteurs de non-lus en hausse (ou erreur) signalés par l'onglet. */
  async compteurs(c: Compteurs): Promise<void> {
    const memoire = { ...MEMOIRE_INITIALE, ...(await this.env.lireMemoire()) };
    memoire.inboxDemandee = true;
    memoire.notificationsDemandees = true;
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

function echec(erreur: string, arret = false): Reponse<never> {
  return { ok: false, erreur, arret, mauvais_compte: false, erreur_vinted: arret };
}

/** Erreur de l'onglet (content script absent, page en rechargement) : jamais d'arrêt du compte. */
export function reponseIndisponible(message: string): Reponse<never> {
  return { ok: false, erreur: message, arret: false, mauvais_compte: false, erreur_vinted: false };
}
