/**
 * Erreurs lors d'un appel à Vinted.
 *
 * - `arret` : réponse inattendue (401, 403, 429, captcha, réponse non JSON). Le compte doit être
 *   arrêté et Lucas prévenu ; aucune nouvelle tentative.
 * - sinon : échec « normal » (validation refusée, donnée introuvable). La tâche passe en erreur,
 *   sans nouvel essai automatique.
 */
export class ErreurVinted extends Error {
  constructor(
    message: string,
    public readonly arret: boolean,
    public readonly statut: number | null = null,
  ) {
    super(message);
    this.name = "ErreurVinted";
  }
}

/** Contrôle métier qui empêche d'agir (taille introuvable, mauvais compte connecté…). */
export class ErreurAction extends Error {
  constructor(
    message: string,
    public readonly mauvaisCompte = false,
  ) {
    super(message);
    this.name = "ErreurAction";
  }
}
