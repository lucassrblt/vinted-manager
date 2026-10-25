/**
 * Favoris (section 9) : lecture des notifications et relance d'un membre (message + offre).
 *
 * L'adresse de la liste des notifications est à vérifier au premier lancement réel : on essaie
 * api.vinted.fr puis www.vinted.fr/web/gateway, et le service worker mémorise celle qui répond.
 */
import { type Attendre, entre } from "../outils";
import type { ClientVinted } from "./client";
import { verifierCompte } from "./compte";
import { ErreurAction, ErreurVinted } from "./erreurs";
import { envoyerOffre } from "./messagerie";

export type SourceNotifications = "api" | "www";

const CHAMPS = [
  "id",
  "entry_type",
  "body",
  "title",
  "subtitle",
  "text",
  "link",
  "url",
  "path",
  "deeplink",
  "subject_type",
  "subject_id",
  "item_id",
  "user_id",
  "sender_id",
  "actor_id",
  "sender_login",
  "user_login",
  "created_at",
  "updated_at",
  "is_read",
];

function liste(corps: Record<string, unknown>): Record<string, unknown>[] | null {
  for (const cle of ["notifications", "items", "data"]) {
    const v = corps[cle];
    if (Array.isArray(v)) return v.filter((n): n is Record<string, unknown> => typeof n === "object" && n !== null);
  }
  return null;
}

export async function lireNotifications(
  client: ClientVinted,
  prefere: SourceNotifications | null,
): Promise<{ source: SourceNotifications; notifications: Record<string, unknown>[] }> {
  const ordre: SourceNotifications[] = prefere === "www" ? ["www", "api"] : ["api", "www"];
  let derniere: unknown = null;
  for (const source of ordre) {
    try {
      const corps = await client.notifications(source);
      const notifications = liste(corps);
      if (!notifications) throw new ErreurVinted(`Liste des notifications illisible (${source}).`, false);
      return {
        source,
        notifications: notifications.map((n) => Object.fromEntries(CHAMPS.filter((k) => k in n).map((k) => [k, n[k]]))),
      };
    } catch (e) {
      if (e instanceof ErreurVinted && e.arret) throw e; // 401, 403, 429, captcha : arrêt, pas d'autre essai
      derniere = e;
    }
  }
  throw derniere instanceof Error ? derniere : new ErreurVinted("Notifications illisibles.", false);
}

export interface Relance {
  conversation_id: string;
  item_id: number;
  membre_id: number;
  texte: string;
  montant: string;
}

/**
 * Dans la conversation ouverte par la page « want_it » : message de relance, puis offre vendeur
 * (2 à 5 s plus tard). Le `transaction_id` est lu dans la conversation.
 */
export async function relancer(
  r: Relance,
  e: { client: ClientVinted; vintedUserId: number | null; attendre: Attendre; aleatoire?: () => number },
): Promise<Record<string, unknown>> {
  await verifierCompte(e.client, e.vintedUserId);
  const conversation = await e.client.conversation(r.conversation_id);
  const bonneAnnonce = (conversation.data?.items ?? []).some((i) => String(i.inventory_item_id) === String(r.item_id));
  const bonMembre = (conversation.opposite_users ?? []).some((u) => String(u.data?.id) === String(r.membre_id));
  if (!bonneAnnonce || !bonMembre) {
    throw new ErreurAction(
      "La conversation ouverte n'est pas celle de ce membre et de cette annonce : rien n'est envoyé.",
    );
  }
  const transaction = conversation.data?.transaction_id;
  if (transaction === null || transaction === undefined || String(transaction) === "") {
    throw new ErreurAction("Transaction introuvable dans la conversation ouverte.");
  }
  const message = await e.client.repondre(r.conversation_id, r.texte);
  await e.attendre(entre(2000, 5000, e.aleatoire));
  try {
    const offre = await envoyerOffre(String(transaction), r.montant, e);
    return {
      conversation_id: r.conversation_id,
      transaction_id: String(transaction),
      message_id: message.id,
      offre_envoyee: true,
      ...offre,
    };
  } catch (err) {
    const prefixe = "Message envoyé, mais offre non envoyée : ";
    if (err instanceof ErreurVinted) throw new ErreurVinted(prefixe + err.message, err.arret, err.statut);
    if (err instanceof ErreurAction) throw new ErreurAction(prefixe + err.message);
    throw err;
  }
}

/** Identifiant de conversation dans l'URL `/inbox/{id}` après la redirection de `want_it`. */
export function conversationDepuisUrl(url: string): string | null {
  const m = /^https:\/\/www\.vinted\.fr\/inbox\/([0-9A-Za-z-]{6,})(?:[/?#]|$)/.exec(url);
  return m && m[1] !== "want_it" ? (m[1] ?? null) : null;
}

/** Page de connexion ou défi anti-robot à la place de la conversation : arrêt. */
export function urlBloquante(url: string): boolean {
  return /\/(signup|login|member\/signup)|captcha|challenge/i.test(url);
}
