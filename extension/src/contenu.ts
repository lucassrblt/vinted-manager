/**
 * Traitement des demandes du service worker dans l'onglet Vinted (testable sans Chrome).
 */
import { type Attendre, base64VersBlob } from "./outils";
import type { PhotoBase64, Reponse, ResultatCompte, VersContenu } from "./protocole";
import { creerBrouillon } from "./vinted/brouillon";
import type { ClientVinted } from "./vinted/client";
import { ErreurAction, ErreurVinted } from "./vinted/erreurs";

export const CACHE_COMPTE_MS = 5 * 60_000;

export interface DependancesContenu {
  client: () => ClientVinted;
  demanderPhoto: (photoId: number) => Promise<Reponse<PhotoBase64>>;
  attendre: Attendre;
  maintenant: () => number;
}

export function versReponse(e: unknown): Reponse<never> {
  if (e instanceof ErreurVinted) return { ok: false, erreur: e.message, arret: e.arret, mauvais_compte: false };
  if (e instanceof ErreurAction) return { ok: false, erreur: e.message, arret: false, mauvais_compte: e.mauvaisCompte };
  return { ok: false, erreur: e instanceof Error ? e.message : String(e), arret: false, mauvais_compte: false };
}

export class Contenu {
  private compte: { valeur: ResultatCompte; date: number } | null = null;

  constructor(private readonly d: DependancesContenu) {}

  async traiter(message: VersContenu): Promise<Reponse> {
    try {
      switch (message.type) {
        case "ping":
          return { ok: true, resultat: null };
        case "compte":
          return { ok: true, resultat: await this.compteCourant() };
        case "brouillon": {
          const client = this.d.client();
          const resultat = await creerBrouillon(message.payload.charge, {
            client,
            photo: (id) => this.photo(id),
            attendre: this.d.attendre,
            vintedUserId: message.payload.vinted_user_id,
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
    if (!Number.isFinite(valeur.id) || valeur.id <= 0) throw new ErreurVinted("Utilisateur Vinted courant illisible.", true);
    this.compte = { valeur, date: this.d.maintenant() };
    return valeur;
  }

  private async photo(photoId: number): Promise<Blob> {
    const r = await this.d.demanderPhoto(photoId);
    if (!r.ok) throw new ErreurAction(`Photo ${photoId} indisponible : ${r.erreur}`);
    return base64VersBlob(r.resultat.base64);
  }
}
