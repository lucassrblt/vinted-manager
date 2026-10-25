import type { ClientVinted } from "./client";
import { ErreurAction, ErreurVinted } from "./erreurs";

/**
 * Contrôle avant chaque lot d'actions : le compte connecté dans ce profil doit être celui attendu.
 * C'est ce qui empêche un article de Lucas d'atterrir sur le compte de sa sœur.
 */
export async function verifierCompte(client: ClientVinted, attendu: number | null): Promise<{ id: number; login: string | null }> {
  const r = await client.utilisateurCourant();
  const id = Number(r?.user?.id);
  if (!Number.isFinite(id) || id <= 0) throw new ErreurVinted("Utilisateur Vinted courant illisible : session expirée ?", true);
  if (attendu === null) {
    throw new ErreurAction("Identifiant Vinted attendu inconnu : confirme le compte dans Paramètres → Automatisation.", true);
  }
  if (id !== attendu) {
    throw new ErreurAction(`Mauvais compte connecté dans ce profil (${r.user.login ?? id}) : aucune action faite.`, true);
  }
  return { id, login: r.user.login ?? null };
}
