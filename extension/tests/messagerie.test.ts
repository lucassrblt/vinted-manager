import { describe, expect, it, vi } from "vitest";

import { Contenu } from "../src/contenu";
import { ClientVinted } from "../src/vinted/client";
import { lireDressing } from "../src/vinted/dressing";
import { ErreurAction, ErreurVinted } from "../src/vinted/erreurs";
import {
  accepterOffre,
  contreOffre,
  reduireConversation,
  reduireInbox,
  refuserOffre,
  repondreMessage,
} from "../src/vinted/messagerie";
import { FauxVinted, capture } from "./fauxVinted";

const CONV = "01a16aa3-daff-79bb-a570-c156d97cb288";

function contexte(faux: FauxVinted, vintedUserId: number | null = 3201823662) {
  return {
    client: new ClientVinted(faux.fetch, { csrf: "c", anonId: "a", siid: null }),
    vintedUserId,
    attendre: vi.fn(async () => undefined),
    aleatoire: () => 0.5,
  };
}

describe("lectures transmises au backend", () => {
  it("inbox réduite au nécessaire (ni photo ni texte des messages)", () => {
    const r = reduireInbox(capture("messaging_inbox").response.body as never) as {
      conversations: Record<string, unknown>[];
    };
    expect(r.conversations[0]).toEqual({
      id: "01a1729a-df35-7e50-84fc-f46b8ec2dc6a",
      conversation_type: "inquiry",
      is_unread_by_current_user: false,
      last_message: { created_at: "2026-10-25T10:31:29.2Z", sender_id: "0", message_type: "legacy_last_message" },
      opposite_users: [{ data: { id: "900000005", login_name: "membre_test_16" } }],
      data: { inventory_items: [{ id: "10475120267", title: "Sweat col rond Uniqlo gris chiné taille L" }] },
    });
    expect(JSON.stringify(r)).not.toContain("images1.vinted.net");
  });

  it("conversation réduite : offres et messages conservés", () => {
    const r = reduireConversation(capture("messaging_conversation").response.body as never) as {
      data: Record<string, unknown>;
      messages: { data: { entity: Record<string, unknown> } }[];
    };
    expect(r.data).toEqual({
      transaction_id: "23517428140",
      current_user_side: "seller",
      items: [{ inventory_item_id: "10475120267", title: "Sweat col rond Uniqlo gris chiné taille L" }],
    });
    expect(r.messages[0]?.data.entity).toMatchObject({ offer_request_id: 5968844926, status: 20, current: true });
    expect(r.messages[1]?.data.entity).toEqual({
      body: "Bonjour n'oublie pas que tu as accepté l'offre ;)",
      user_id: 3201823662,
    });
    expect(JSON.stringify(r)).not.toContain("images1.vinted.net");
  });

  it("dressing : toutes les pages, 2 à 4 s entre deux pages, complet seulement si tout est lu", async () => {
    const faux = new FauxVinted();
    let page = 0;
    const base = capture("wardrobe_items").response.body as { items: unknown[] };
    faux.sur("GET", /wardrobe/, () => {
      page += 1;
      return {
        body: {
          items: page === 1 ? base.items.slice(0, 2) : base.items.slice(2),
          pagination: { current_page: page, total_pages: 2, total_entries: 4, per_page: 2 },
        },
      };
    });
    const attendre = vi.fn(async () => undefined);
    const r = await lireDressing(contexte(faux).client, 3201823662, attendre, () => 0.5);
    expect(r.items).toHaveLength(4);
    expect(r.complet).toBe(true);
    expect(attendre).toHaveBeenCalledWith(3000);
    expect(faux.appels.map((a) => a.url)).toEqual([
      "https://www.vinted.fr/api/v2/wardrobe/3201823662/items?page=1&per_page=20",
      "https://www.vinted.fr/api/v2/wardrobe/3201823662/items?page=2&per_page=20",
    ]);
    expect(r.items[3]).toMatchObject({ id: 10495633803, is_draft: false, price: { amount: "10.0" } });
  });
});

describe("exécution des décisions de l'assistant", () => {
  it("réponse dans la conversation (nouvelle API de messagerie)", async () => {
    const faux = new FauxVinted();
    const r = await repondreMessage({ conversation_id: CONV, texte: "Oui, toujours dispo !" }, contexte(faux));
    expect(r).toEqual({ message_id: "01a17299-d3db-70f0-892d-72e4df04863a" });
    const envoi = faux.ecritures()[0];
    expect(envoi?.url).toBe(`https://api.vinted.fr/messaging/main/conversations/${CONV}/replies`);
    expect(envoi?.corps).toEqual({
      content: "Oui, toujours dispo !",
      is_personal_data_sharing_check_skipped: false,
      photo_temp_uuids: null,
    });
    expect(envoi?.entetes).toMatchObject({ platform: "web", "x-next-app": "marketplace-web" });
  });

  it("acceptation d'une offre reçue", async () => {
    const faux = new FauxVinted();
    expect(await accepterOffre({ transaction_id: 23563143719, offer_request_id: 5983786317 }, contexte(faux))).toEqual({
      statut: 20,
    });
    expect(faux.ecritures().map((a) => `${a.methode} ${a.url}`)).toEqual([
      "PUT https://www.vinted.fr/api/v2/transactions/23563143719/offer_requests/5983786317/accept",
    ]);
  });

  it("refus puis message poli, quelques secondes plus tard", async () => {
    const faux = new FauxVinted();
    const e = contexte(faux);
    const r = await refuserOffre(
      { transaction_id: 23563143719, offer_request_id: 5983780453, conversation_id: CONV, texte: "Merci, mais non." },
      e,
    );
    expect(r).toMatchObject({ statut: 30, message_envoye: true });
    expect(faux.ecritures().map((a) => a.methode)).toEqual(["PUT", "POST"]);
    expect(e.attendre).toHaveBeenCalledWith(5500);
  });

  it("message non envoyé après le refus : erreur explicite, sans nouvel essai", async () => {
    const faux = new FauxVinted().sur("POST", /replies$/, () => ({ status: 403, body: {} }));
    const err = (await refuserOffre(
      { transaction_id: 1, offer_request_id: 2, conversation_id: CONV, texte: "Non merci" },
      contexte(faux),
    ).catch((x: unknown) => x)) as ErreurVinted;
    expect(err.message).toMatch(/^Offre refusée, mais message non envoyé/);
    expect(err.arret).toBe(true);
    expect(faux.ecritures()).toHaveLength(2);
  });

  it("contre-offre dans les limites de Vinted", async () => {
    const faux = new FauxVinted();
    const r = await contreOffre({ transaction_id: 23563143719, montant: "7" }, contexte(faux));
    expect(r).toEqual({ offer_id: 38066597320, prix: "7.0" });
    expect(faux.appels.map((a) => `${a.methode} ${a.url.replace("https://www.vinted.fr", "")}`)).toEqual([
      "GET /api/v2/users/current",
      "GET /api/v2/transactions/23563143719/offers/seller_options",
      "POST /api/v2/transactions/23563143719/offers",
    ]);
    expect(faux.ecritures()[0]?.corps).toEqual({ offer: { price: "7", currency: "EUR" } });
  });

  it("contre-offre hors limites : rien n'est envoyé", async () => {
    const faux = new FauxVinted();
    const err = await contreOffre({ transaction_id: 1, montant: "500" }, contexte(faux)).catch((x: unknown) => x);
    expect(err).toBeInstanceOf(ErreurAction);
    expect(faux.ecritures()).toHaveLength(0);
  });

  it("mauvais compte : aucune écriture", async () => {
    const faux = new FauxVinted();
    await repondreMessage({ conversation_id: CONV, texte: "x" }, contexte(faux, 1)).catch(() => undefined);
    expect(faux.ecritures()).toHaveLength(0);
  });
});

describe("relevé des compteurs de non-lus", () => {
  it("prévient le service worker seulement quand un compteur augmente", async () => {
    const faux = new FauxVinted();
    let n = 2;
    faux.sur("GET", /messaging\/main\/users\/unread_count/, () => ({ body: { unread_count: n } }));
    const signaler = vi.fn();
    let t = 0;
    const c = new Contenu({
      client: () => new ClientVinted(faux.fetch, { csrf: "c", anonId: "a", siid: null }),
      demanderPhoto: async () => ({ ok: false, erreur: "x", arret: false, mauvais_compte: false }),
      attendre: async () => undefined,
      maintenant: () => t,
      signaler,
    });
    await c.releve();
    expect(faux.appels).toHaveLength(0); // pas de consigne de surveillance : rien
    await c.traiter({ type: "surveillance", id: "1", payload: { actif: true, nuit: false } });
    await c.releve();
    await c.releve();
    expect(signaler).not.toHaveBeenCalled();
    n = 3;
    await c.releve();
    expect(signaler).toHaveBeenCalledWith({ messages: 3, notifications: 0 });
    t = 3 * 60_000; // plus de consigne depuis 2 min : la surveillance s'arrête
    const avant = faux.appels.length;
    await c.releve();
    expect(faux.appels).toHaveLength(avant);
  });
});
