/**
 * Client unique de l'API privée Vinted, utilisé depuis le content script (onglet www.vinted.fr).
 *
 * Les appels partent de la page avec les cookies du navigateur (`credentials: "include"`) : aucun
 * identifiant n'est lu ni stocké par l'extension, en dehors du jeton CSRF et de l'`anon_id` que le
 * site envoie lui-même en en-tête. Seules les routes de la section 13 de la spécification sont utilisées.
 */
import { ErreurVinted } from "./erreurs";

export const WWW = "https://www.vinted.fr";
export const API = "https://api.vinted.fr";

export type Fetch = (url: string, init: RequestInit) => Promise<Response>;

export interface ContexteVinted {
  csrf: string | null;
  anonId: string | null;
  siid: string | null;
}

// --- Types des réponses utilisées -------------------------------------------------------------

export interface Montant {
  amount: string;
  currency_code: string;
}

export interface UtilisateurCourant {
  user: { id: number; login?: string };
}

export interface PhotoUpload {
  id: number;
  image_uuid: string;
  is_suspicious?: boolean;
}

export interface OptionAttribut {
  id: number;
  title: string;
  type?: string;
  options?: OptionAttribut[];
}

export interface Attribut {
  code: string;
  configuration: {
    required?: boolean;
    selection_type?: string;
    selection_limit?: number;
    options?: OptionAttribut[];
  } | null;
}

export interface Marque {
  id: number;
  title: string;
}

export interface Couleur {
  id: number;
  title: string;
}

export interface SuggestionsAttributs {
  brands?: Marque[];
  prefill_brand?: Marque | null;
  colors?: Couleur[];
  dynamic_attributes?: { code: string; suggested_option_ids?: string[]; prefill_option_ids?: string[] }[];
}

export interface PhotoAssignee {
  id: number;
  orientation: number;
  ai_detected?: boolean;
  digital_source_type?: string[];
  c2pa_read_error?: string;
}

export interface ObjetBrouillon {
  id: number | null;
  currency: "EUR";
  temp_uuid: string;
  title: string;
  description: string;
  brand_id: number;
  brand: string;
  catalog_id: number;
  isbn: null;
  ai_photo: boolean;
  price: string;
  package_size_id: number;
  shipment_prices: { domestic: null; international: null };
  color_ids: number[];
  assigned_photos: PhotoAssignee[];
  measurement_length: null;
  measurement_width: null;
  item_attributes: { code: string; ids: number[] }[];
  manufacturer: null;
  manufacturer_labelling: null;
}

export interface ArticleDressing {
  id: number;
  title: string;
  is_draft: boolean;
  is_closed?: boolean;
  is_hidden?: boolean;
  is_reserved?: boolean;
  item_closing_action?: string | null;
  price: Montant;
  favourite_count?: number;
  view_count?: number;
  brand?: string;
  size?: string;
  status?: string;
  photos?: { id: number; full_size_url?: string; url?: string }[];
}

export interface PageDressing {
  items: ArticleDressing[];
  pagination: { current_page: number; total_pages: number; total_entries: number; per_page: number };
}

export interface MessageConversation {
  id: string;
  created_at: string;
  message_type: string;
  sender_id: string;
  data?: { entity?: Record<string, unknown>; entity_type?: string };
}

export interface Conversation {
  id: string;
  data: {
    transaction_id?: string | number | null;
    current_user_side?: string;
    items?: { inventory_item_id: string; title?: string }[];
    total_price?: Montant;
  };
  opposite_users?: { data: { id: string; login_name?: string } }[];
  messages: MessageConversation[];
}

export interface ConversationInbox {
  id: string;
  conversation_type?: string;
  is_unread_by_current_user?: boolean;
  last_message?: { created_at: string; sender_id: string; message_type?: string; data?: { content?: string } };
  opposite_users?: { data: { id: string; login_name?: string } }[];
  data?: { inventory_items?: { id: string; title?: string }[] };
  statuses?: unknown[];
}

export interface Inbox {
  conversations: ConversationInbox[];
  pagination?: { has_next?: boolean; next_cursor?: string | null };
}

export interface OffreEnvoyee {
  offer: { id: number; price: Montant; transaction_id: number; user_msg_thread_id?: number };
}

// --- Client -----------------------------------------------------------------------------------

const MOTS_CAPTCHA = ["captcha", "datadome", "cf-challenge", "are you a robot"];

export class ClientVinted {
  constructor(
    private readonly fetch: Fetch,
    private readonly contexte: ContexteVinted,
  ) {}

  private entetes(base: string, json: boolean): Record<string, string> {
    const h: Record<string, string> = { accept: "application/json, text/plain, */*", locale: "fr-FR" };
    if (json) h["content-type"] = "application/json";
    if (this.contexte.csrf) h["x-csrf-token"] = this.contexte.csrf;
    if (this.contexte.anonId) h["x-anon-id"] = this.contexte.anonId;
    if (this.contexte.siid) h["siid"] = this.contexte.siid;
    if (base === API) {
      h["platform"] = "web";
      h["x-next-app"] = "marketplace-web";
    }
    return h;
  }

  /** Un appel, sans aucune nouvelle tentative. Lève ErreurVinted (avec `arret` si inattendu). */
  async appeler<T>(
    methode: "GET" | "POST" | "PUT",
    base: string,
    chemin: string,
    corps?: unknown,
    formulaire?: FormData,
  ): Promise<T> {
    const url = base + chemin;
    let res: Response;
    try {
      res = await this.fetch(url, {
        method: methode,
        credentials: "include",
        headers: this.entetes(base, corps !== undefined),
        body: formulaire ?? (corps !== undefined ? JSON.stringify(corps) : undefined),
      });
    } catch {
      throw new ErreurVinted(`Vinted injoignable (${methode} ${chemin}).`, false);
    }
    const texte = await res.text();
    if (res.status === 401)
      throw new ErreurVinted("Session Vinted expirée (401) : reconnecte-toi dans ce profil Chrome.", true, 401);
    if (res.status === 403) throw new ErreurVinted(`Vinted a refusé l'accès (403) sur ${chemin}.`, true, 403);
    if (res.status === 429)
      throw new ErreurVinted(`Trop de requêtes : Vinted limite le débit (429) sur ${chemin}.`, true, 429);
    // Route absente : ce n'est pas un signe de blocage (ex. adresse des notifications à vérifier).
    if (res.status === 404) throw new ErreurVinted(`Route Vinted introuvable (404) : ${chemin}.`, false, 404);
    const minuscule = texte.slice(0, 5000).toLowerCase();
    let donnees: unknown;
    try {
      donnees = texte === "" ? {} : JSON.parse(texte);
    } catch {
      const captcha = MOTS_CAPTCHA.some((m) => minuscule.includes(m));
      throw new ErreurVinted(
        captcha ? `Captcha Vinted détecté sur ${chemin}.` : `Réponse Vinted non JSON (${res.status}) sur ${chemin}.`,
        true,
        res.status,
      );
    }
    if (typeof donnees !== "object" || donnees === null) {
      throw new ErreurVinted(`Réponse Vinted inattendue sur ${chemin}.`, true, res.status);
    }
    const objet = donnees as Record<string, unknown>;
    // Défi anti-robot renvoyé en JSON (DataDome : {"url": "https://geo.captcha-delivery.com/…"}).
    if (minuscule.includes("captcha-delivery") || (typeof objet.url === "string" && /captcha/i.test(objet.url))) {
      throw new ErreurVinted(`Captcha Vinted détecté sur ${chemin}.`, true, res.status);
    }
    if (!res.ok) {
      throw new ErreurVinted(`Vinted a refusé la demande (${res.status}) : ${messageDe(objet)}`, false, res.status);
    }
    if (typeof objet.code === "number" && objet.code !== 0) {
      throw new ErreurVinted(
        `Vinted a refusé la demande (code ${objet.code}) : ${messageDe(objet)}`,
        false,
        res.status,
      );
    }
    return donnees as T;
  }

  // Compte
  utilisateurCourant(): Promise<UtilisateurCourant> {
    return this.appeler("GET", WWW, "/api/v2/users/current");
  }

  // Création d'un brouillon (13.2)
  envoyerPhoto(jpeg: Blob, tempUuid: string): Promise<PhotoUpload> {
    const f = new FormData();
    f.append("photo[type]", "item");
    f.append("photo[file]", jpeg, "photo.jpg");
    f.append("photo[temp_uuid]", tempUuid);
    return this.appeler("POST", WWW, "/api/v2/photos", undefined, f);
  }

  suggestionsCategories(imageIds: string[], session: string): Promise<{ prefill_categories?: number[] }> {
    return this.appeler("POST", WWW, "/api/v2/item_upload/suggestions/categories", {
      image_metadata: imageIds.map((id) => ({ image_id: id, orientation: "0" })),
      upload_session_id: session,
    });
  }

  attributs(catalogId: number): Promise<{ attributes: Attribut[] }> {
    return this.appeler("POST", WWW, "/api/v2/item_upload/attributes", {
      attributes: [{ code: "category", value: [catalogId] }],
    });
  }

  suggestionsAttributs(p: {
    titre: string;
    description: string;
    catalogId: number;
    imageIds: string[];
    session: string;
  }): Promise<SuggestionsAttributs> {
    return this.appeler("POST", WWW, "/api/v2/item_upload/suggestions/attributes", {
      title: p.titre,
      description: p.description,
      category_id: p.catalogId,
      suggested_category_id: p.catalogId,
      image_metadata: p.imageIds.map((id) => ({ image_id: id, orientation: "0" })),
      upload_session_id: p.session,
      attributes: [
        { code: "category", ids: [String(p.catalogId)] },
        { code: "brand", ids: [] },
        { code: "size", ids: [] },
        { code: "condition", ids: [] },
        { code: "color", ids: [] },
        { code: "material", ids: [] },
      ],
    });
  }

  marques(catalogId: number): Promise<{ brands: Marque[] }> {
    return this.appeler("GET", WWW, `/api/v2/item_upload/brands?category_id=${catalogId}`);
  }

  couleurs(): Promise<{ colors: Couleur[] }> {
    return this.appeler("GET", WWW, "/api/v2/item_upload/colors");
  }

  creerBrouillon(draft: ObjetBrouillon, session: string): Promise<{ draft: { id: number } }> {
    return this.appeler("POST", WWW, "/api/v2/item_upload/drafts", { draft, parcel: null, upload_session_id: session });
  }

  // Publication, modification, suppression (13.3)
  publierBrouillon(draft: ObjetBrouillon, session: string): Promise<{ item: { id: number } }> {
    return this.appeler("POST", WWW, `/api/v2/item_upload/drafts/${draft.id}/completion`, {
      draft,
      push_up: false,
      parcel: null,
      upload_session_id: session,
    });
  }

  supprimerArticle(itemId: number): Promise<{ code: number }> {
    return this.appeler("POST", WWW, `/api/v2/items/${itemId}/delete`);
  }

  lireArticle(itemId: number): Promise<{ item: Record<string, unknown> }> {
    return this.appeler("GET", WWW, `/api/v2/items/${itemId}?localization=fr-FR`);
  }

  modifierArticle(item: Record<string, unknown>, session: string): Promise<{ item: { id: number } }> {
    return this.appeler("PUT", WWW, `/api/v2/item_upload/items/${String(item.id)}`, {
      item,
      push_up: false,
      parcel: null,
      upload_session_id: session,
    });
  }

  // Dressing
  dressing(userId: number, page: number, parPage = 20): Promise<PageDressing> {
    return this.appeler("GET", WWW, `/api/v2/wardrobe/${userId}/items?page=${page}&per_page=${parPage}`);
  }

  // Offres
  optionsVendeur(transactionId: string | number): Promise<{
    seller_offer_options: { min_price: Montant; max_price: Montant };
  }> {
    return this.appeler("GET", WWW, `/api/v2/transactions/${transactionId}/offers/seller_options`);
  }

  envoyerOffre(transactionId: string | number, prix: string): Promise<OffreEnvoyee> {
    return this.appeler("POST", WWW, `/api/v2/transactions/${transactionId}/offers`, {
      offer: { price: prix, currency: "EUR" },
    });
  }

  accepterOffre(
    transactionId: string | number,
    offerRequestId: string | number,
  ): Promise<{
    offer_request: { status: number };
  }> {
    return this.appeler("PUT", WWW, `/api/v2/transactions/${transactionId}/offer_requests/${offerRequestId}/accept`);
  }

  refuserOffre(
    transactionId: string | number,
    offerRequestId: string | number,
  ): Promise<{
    offer_request: { status: number };
  }> {
    return this.appeler("PUT", WWW, `/api/v2/transactions/${transactionId}/offer_requests/${offerRequestId}/reject`);
  }

  // Messagerie (api.vinted.fr)
  inbox(): Promise<Inbox> {
    return this.appeler("GET", API, "/messaging/main/inbox");
  }

  conversation(id: string): Promise<Conversation> {
    return this.appeler("GET", API, `/messaging/main/conversations/${id}`);
  }

  repondre(conversationId: string, texte: string): Promise<{ id: string; conversation_id: string }> {
    return this.appeler("POST", API, `/messaging/main/conversations/${conversationId}/replies`, {
      content: texte,
      is_personal_data_sharing_check_skipped: false,
      photo_temp_uuids: null,
    });
  }

  nonLusMessages(): Promise<{ unread_count: number }> {
    return this.appeler("GET", API, "/messaging/main/users/unread_count");
  }

  nonLusNotifications(): Promise<{ count: number }> {
    return this.appeler("GET", API, "/inbox-notifications/v1/notifications/unread_count");
  }

  /** Liste des notifications : deux adresses possibles (à vérifier au premier lancement réel). */
  notifications(source: "api" | "www", page = 1, parPage = 20): Promise<Record<string, unknown>> {
    return source === "api"
      ? this.appeler("GET", API, `/inbox-notifications/v1/notifications?page=${page}&per_page=${parPage}`)
      : this.appeler("GET", WWW, `/web/gateway/inbox-notifications/v1/notifications?page=${page}&per_page=${parPage}`);
  }
}

function messageDe(objet: Record<string, unknown>): string {
  for (const cle of ["message", "error", "error_description"]) {
    if (typeof objet[cle] === "string" && objet[cle]) return objet[cle] as string;
  }
  const erreurs = objet.errors;
  if (Array.isArray(erreurs) && erreurs.length) return JSON.stringify(erreurs).slice(0, 300);
  return "raison non précisée";
}

/** Lit le jeton CSRF, l'anon_id et le siid tels que le site les envoie. */
export function lireContexte(doc: Document): ContexteVinted {
  const meta = doc.querySelector('meta[name="csrf-token"]')?.getAttribute("content") ?? null;
  const html = doc.documentElement?.innerHTML ?? "";
  const csrf = meta || (/CSRF_TOKEN\\?"\s*:\s*\\?"([^"\\]+)/.exec(html)?.[1] ?? null);
  const anonId = /(?:^|;\s*)anon_id=([^;]+)/.exec(doc.cookie)?.[1] ?? null;
  const siid = /\bsiid\\?"\s*:\s*\\?"([0-9a-f-]{36})/i.exec(html)?.[1] ?? null;
  return { csrf, anonId: anonId ? decodeURIComponent(anonId) : null, siid };
}
