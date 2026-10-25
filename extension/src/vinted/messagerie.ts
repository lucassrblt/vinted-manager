/**
 * Messagerie et offres reçues (section 13.3) : lectures pour le backend, exécution de ses décisions.
 * Les données transmises au backend sont réduites au nécessaire (pas de photos ni d'URL d'avatar).
 */
import { type Attendre, entre } from "../outils";
import type { ClientVinted, Conversation, Inbox } from "./client";
import { verifierCompte } from "./compte";
import { ErreurAction, ErreurVinted } from "./erreurs";

const STATUT_ACCEPTEE = 20;
const STATUT_REFUSEE = 30;

function utilisateurs(liste: { data: { id: string; login_name?: string } }[] | undefined) {
  return (liste ?? []).map((u) => ({ data: { id: u.data?.id, login_name: u.data?.login_name } }));
}

export function reduireInbox(inbox: Inbox): Record<string, unknown> {
  return {
    conversations: (inbox.conversations ?? []).map((c) => ({
      id: c.id,
      conversation_type: c.conversation_type,
      is_unread_by_current_user: c.is_unread_by_current_user,
      last_message: c.last_message
        ? {
            created_at: c.last_message.created_at,
            sender_id: c.last_message.sender_id,
            message_type: c.last_message.message_type,
          }
        : null,
      opposite_users: utilisateurs(c.opposite_users),
      data: { inventory_items: (c.data?.inventory_items ?? []).map((i) => ({ id: i.id, title: i.title })) },
    })),
  };
}

const CHAMPS_ENTITE = ["body", "offer_request_id", "price", "status", "transaction_id", "user_id", "current"];

export function reduireConversation(c: Conversation): Record<string, unknown> {
  return {
    id: c.id,
    data: {
      transaction_id: c.data?.transaction_id ?? null,
      current_user_side: c.data?.current_user_side,
      items: (c.data?.items ?? []).map((i) => ({ inventory_item_id: i.inventory_item_id, title: i.title })),
    },
    opposite_users: utilisateurs(c.opposite_users),
    messages: (c.messages ?? []).map((m) => {
      const entite = (m.data?.entity ?? {}) as Record<string, unknown>;
      return {
        id: m.id,
        created_at: m.created_at,
        message_type: m.message_type,
        sender_id: m.sender_id,
        data: {
          entity_type: m.data?.entity_type,
          entity: Object.fromEntries(CHAMPS_ENTITE.filter((k) => k in entite).map((k) => [k, entite[k]])),
          content: (m.data as { content?: unknown } | undefined)?.content,
        },
      };
    }),
  };
}

export interface ContexteAction {
  client: ClientVinted;
  vintedUserId: number | null;
  attendre: Attendre;
  aleatoire?: () => number;
}

function texte(payload: Record<string, unknown>, cle: string): string {
  const v = payload[cle];
  if (typeof v !== "string" || !v.trim()) throw new ErreurAction(`Donnée manquante dans la tâche : ${cle}.`);
  return v.trim();
}

function identifiant(payload: Record<string, unknown>, cle: string): string {
  const v = payload[cle];
  if ((typeof v !== "number" && typeof v !== "string") || String(v) === "") {
    throw new ErreurAction(`Donnée manquante dans la tâche : ${cle}.`);
  }
  return String(v);
}

export async function repondreMessage(p: Record<string, unknown>, e: ContexteAction): Promise<Record<string, unknown>> {
  await verifierCompte(e.client, e.vintedUserId);
  const r = await e.client.repondre(texte(p, "conversation_id"), texte(p, "texte"));
  return { message_id: r.id };
}

export async function accepterOffre(p: Record<string, unknown>, e: ContexteAction): Promise<Record<string, unknown>> {
  await verifierCompte(e.client, e.vintedUserId);
  const r = await e.client.accepterOffre(identifiant(p, "transaction_id"), identifiant(p, "offer_request_id"));
  if (r.offer_request?.status !== STATUT_ACCEPTEE) {
    throw new ErreurVinted(`Offre non acceptée par Vinted (statut ${String(r.offer_request?.status)}).`, false);
  }
  return { statut: STATUT_ACCEPTEE };
}

/** Refus Vinted, puis message poli (quelques secondes plus tard, comme une personne). */
export async function refuserOffre(p: Record<string, unknown>, e: ContexteAction): Promise<Record<string, unknown>> {
  await verifierCompte(e.client, e.vintedUserId);
  const r = await e.client.refuserOffre(identifiant(p, "transaction_id"), identifiant(p, "offer_request_id"));
  if (r.offer_request?.status !== STATUT_REFUSEE) {
    throw new ErreurVinted(`Offre non refusée par Vinted (statut ${String(r.offer_request?.status)}).`, false);
  }
  const message = typeof p.texte === "string" ? p.texte.trim() : "";
  if (!message) return { statut: STATUT_REFUSEE, message_envoye: false };
  await e.attendre(entre(3000, 8000, e.aleatoire));
  try {
    const envoi = await e.client.repondre(texte(p, "conversation_id"), message);
    return { statut: STATUT_REFUSEE, message_envoye: true, message_id: envoi.id };
  } catch (err) {
    if (err instanceof ErreurVinted) {
      throw new ErreurVinted(`Offre refusée, mais message non envoyé : ${err.message}`, err.arret, err.statut);
    }
    throw err;
  }
}

/** Offre vendeur sur la transaction (contre-offre ou offre à un favori), dans les limites de Vinted. */
export async function envoyerOffre(
  transactionId: string,
  montant: string,
  e: ContexteAction,
): Promise<Record<string, unknown>> {
  const valeur = Number(montant);
  if (!Number.isFinite(valeur) || valeur <= 0) throw new ErreurAction(`Montant invalide : ${montant}.`);
  const options = (await e.client.optionsVendeur(transactionId)).seller_offer_options;
  const min = Number(options?.min_price?.amount);
  const max = Number(options?.max_price?.amount);
  if (!Number.isFinite(min) || !Number.isFinite(max))
    throw new ErreurVinted("Limites d'offre Vinted illisibles.", false);
  if (valeur < min || valeur > max) {
    throw new ErreurAction(`Montant ${montant} € hors des limites de Vinted (${min} à ${max} €).`);
  }
  const r = await e.client.envoyerOffre(transactionId, montant);
  return { offer_id: r.offer?.id, prix: r.offer?.price?.amount };
}

export async function contreOffre(p: Record<string, unknown>, e: ContexteAction): Promise<Record<string, unknown>> {
  await verifierCompte(e.client, e.vintedUserId);
  return envoyerOffre(identifiant(p, "transaction_id"), texte(p, "montant"), e);
}
