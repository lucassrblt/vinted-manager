/**
 * Traitement des demandes du service worker dans l'onglet Vinted (testable sans Chrome).
 */
import { type Attendre, base64VersBlob, entre } from "./outils";
import type { Compteurs, Echec, PhotoBase64, RefPhoto, Reponse, ResultatCompte, Tache, VersContenu } from "./protocole";
import { type ChargeBrouillon, creerBrouillon } from "./vinted/brouillon";
import type { ClientVinted } from "./vinted/client";
import { verifierCompte } from "./vinted/compte";
import { lireDressing } from "./vinted/dressing";
import { lireNotifications, relancer } from "./vinted/favoris";
import { ErreurAction, ErreurVinted } from "./vinted/erreurs";
import { modifierPrix } from "./vinted/prix";
import { type ChargeRepublication, ErreurPartielle, republier } from "./vinted/republication";
import {
  accepterOffre,
  contreOffre,
  messageApresVente,
  reduireConversation,
  reduireInbox,
  refuserOffre,
  repondreMessage,
} from "./vinted/messagerie";

export interface Execution {
  client: ClientVinted;
  vintedUserId: number | null;
  photo: (ref: RefPhoto) => Promise<Blob>;
  attendre: Attendre;
  aleatoire?: () => number;
}

export type Executeur = (tache: Tache, e: Execution) => Promise<Record<string, unknown>>;

/** Exécuteurs par type de tâche (complétés à chaque phase). */
export const EXECUTEURS: Record<string, Executeur> = {
  repondre_message: (t, e) => repondreMessage(t.payload, e),
  accepter_offre: (t, e) => accepterOffre(t.payload, e),
  refuser_offre: (t, e) => refuserOffre(t.payload, e),
  contre_offre: (t, e) => contreOffre(t.payload, e),
  modifier_prix: (t, e) => modifierPrix(t.payload, e),
  message_apres_vente: (t, e) => messageApresVente(t.payload, e),
  republication: (t, e) =>
    republier(t.payload as unknown as ChargeRepublication, {
      client: e.client,
      vintedUserId: e.vintedUserId,
      photo: (index) => e.photo({ tache_id: t.id, index }),
      attendre: e.attendre,
      aleatoire: e.aleatoire,
    }),
  brouillon: async (tache, e) => ({
    ...(await creerBrouillon(tache.payload as unknown as ChargeBrouillon, {
      client: e.client,
      photo: (photo_id) => e.photo({ photo_id }),
      attendre: e.attendre,
      vintedUserId: e.vintedUserId,
    })),
  }),
};

export const CACHE_COMPTE_MS = 5 * 60_000;
// Compteurs de non-lus : toutes les 15 à 30 s en journée, toutes les 5 min la nuit.
export const RELEVE_JOUR_MS: [number, number] = [15_000, 30_000];
export const RELEVE_NUIT_MS = 5 * 60_000;
// Sans nouvelle du service worker pendant ce délai, la surveillance s'arrête d'elle-même.
export const VALIDITE_SURVEILLANCE_MS = 2 * 60_000;
export const ECHECS_RELEVE_MAX = 3;

export interface DependancesContenu {
  client: () => ClientVinted;
  demanderPhoto: (ref: RefPhoto) => Promise<Reponse<PhotoBase64>>;
  attendre: Attendre;
  maintenant: () => number;
  /** Relance différée de la surveillance (setTimeout dans la page). */
  planifier?: (fn: () => void, ms: number) => void;
  /** Prévient le service worker d'un changement des compteurs. */
  signaler?: (c: Compteurs) => void;
  aleatoire?: () => number;
}

export function versReponse(e: unknown): Echec {
  if (e instanceof ErreurPartielle) {
    return { ...versReponse(e.cause), erreur: e.message, resultat: e.partiel };
  }
  if (e instanceof ErreurVinted) {
    return { ok: false, erreur: e.message, arret: e.arret, mauvais_compte: false, erreur_vinted: true };
  }
  if (e instanceof ErreurAction) {
    return { ok: false, erreur: e.message, arret: false, mauvais_compte: e.mauvaisCompte, erreur_vinted: false };
  }
  return {
    ok: false,
    erreur: e instanceof Error ? e.message : String(e),
    arret: false,
    mauvais_compte: false,
    erreur_vinted: false,
  };
}

export class Contenu {
  private compte: { valeur: ResultatCompte; date: number } | null = null;
  private surveillance = { actif: false, nuit: false, jusqua: 0 };
  private derniers: { messages: number; notifications: number } | null = null;
  private boucle = false;
  private echecsReleve = 0;

  constructor(private readonly d: DependancesContenu) {}

  /** Un relevé des compteurs de non-lus ; prévient le service worker s'ils augmentent. */
  async releve(): Promise<void> {
    const s = this.surveillance;
    if (!s.actif || this.d.maintenant() > s.jusqua) return;
    const client = this.d.client();
    try {
      const [m, n] = await Promise.all([client.nonLusMessages(), client.nonLusNotifications()]);
      const actuels = { messages: Number(m.unread_count) || 0, notifications: Number(n.count) || 0 };
      this.echecsReleve = 0;
      const avant = this.derniers;
      this.derniers = actuels;
      if (avant && (actuels.messages > avant.messages || actuels.notifications > avant.notifications)) {
        this.d.signaler?.(actuels);
      }
    } catch (e) {
      const r = versReponse(e);
      this.echecsReleve += 1;
      // Une réponse bloquée sans en-têtes CORS ressemble à une coupure réseau : au 3e échec d'affilée, arrêt.
      if (r.arret || this.echecsReleve >= ECHECS_RELEVE_MAX) {
        const erreur = r.arret
          ? r.erreur
          : `Vinted ne répond plus (${this.echecsReleve} relevés d'affilée) : ${r.erreur}`;
        this.d.signaler?.({ messages: null, notifications: null, erreur, arret: true });
        this.echecsReleve = 0;
      }
    }
  }

  private lancerBoucle(): void {
    if (this.boucle || !this.d.planifier) return;
    this.boucle = true;
    const etape = async (): Promise<void> => {
      await this.releve();
      const delai = this.surveillance.nuit ? RELEVE_NUIT_MS : entre(...RELEVE_JOUR_MS, this.d.aleatoire);
      this.d.planifier?.(() => void etape(), delai);
    };
    this.d.planifier(() => void etape(), entre(...RELEVE_JOUR_MS, this.d.aleatoire));
  }

  async traiter(message: VersContenu): Promise<Reponse> {
    try {
      switch (message.type) {
        case "ping":
          return { ok: true, resultat: null };
        case "compte":
          return { ok: true, resultat: await this.compteCourant() };
        case "inbox":
          return { ok: true, resultat: reduireInbox(await this.d.client().inbox()) };
        case "conversation":
          return {
            ok: true,
            resultat: reduireConversation(await this.d.client().conversation(message.payload.id)),
          };
        case "notifications":
          return { ok: true, resultat: await lireNotifications(this.d.client(), message.payload.source) };
        case "verifier_compte":
          this.compte = null; // relu sans cache : la navigation qui suit crée une conversation
          return { ok: true, resultat: await verifierCompte(this.d.client(), message.payload.vinted_user_id) };
        case "relance": {
          const { vinted_user_id, ...relance } = message.payload;
          const resultat = await relancer(relance, {
            client: this.d.client(),
            vintedUserId: vinted_user_id,
            attendre: this.d.attendre,
            aleatoire: this.d.aleatoire,
          });
          return { ok: true, resultat };
        }
        case "surveillance":
          this.surveillance = { ...message.payload, jusqua: this.d.maintenant() + VALIDITE_SURVEILLANCE_MS };
          this.lancerBoucle();
          return { ok: true, resultat: null };
        case "dressing":
          return { ok: true, resultat: await lireDressing(this.d.client(), message.payload.user_id, this.d.attendre) };
        case "executer": {
          const { tache, vinted_user_id } = message.payload;
          const executeur = EXECUTEURS[tache.type];
          if (!executeur) throw new ErreurAction(`Type de tâche non pris en charge par cette version : ${tache.type}.`);
          const resultat = await executeur(tache, {
            client: this.d.client(),
            vintedUserId: vinted_user_id,
            photo: (ref) => this.photo(ref),
            attendre: this.d.attendre,
            aleatoire: this.d.aleatoire,
          });
          return { ok: true, resultat };
        }
      }
    } catch (e) {
      if (e instanceof ErreurVinted && e.arret) this.compte = null;
      return versReponse(e);
    }
  }

  /** `users/current`, relu au plus toutes les 5 minutes pour le signal de vie. */
  private async compteCourant(): Promise<ResultatCompte> {
    if (this.compte && this.d.maintenant() - this.compte.date < CACHE_COMPTE_MS) return this.compte.valeur;
    const r = await this.d.client().utilisateurCourant();
    const valeur = { id: Number(r.user.id), login: r.user.login ?? null };
    if (!Number.isFinite(valeur.id) || valeur.id <= 0)
      throw new ErreurVinted("Utilisateur Vinted courant illisible.", true);
    this.compte = { valeur, date: this.d.maintenant() };
    return valeur;
  }

  private async photo(ref: RefPhoto): Promise<Blob> {
    const r = await this.d.demanderPhoto(ref);
    if (!r.ok) throw new ErreurAction(`Photo ${JSON.stringify(ref)} indisponible : ${r.erreur}`);
    return base64VersBlob(r.resultat.base64);
  }
}
