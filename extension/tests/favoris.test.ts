import { describe, expect, it, vi } from "vitest";

import { ClientVinted } from "../src/vinted/client";
import { ErreurVinted } from "../src/vinted/erreurs";
import { conversationDepuisUrl, lireNotifications, relancer, urlBloquante } from "../src/vinted/favoris";
import { FauxVinted } from "./fauxVinted";

const client = (faux: FauxVinted) => new ClientVinted(faux.fetch, { csrf: "c", anonId: "a", siid: null });
const NOTIF = {
  id: "n1",
  body: "<b>marie</b> a ajouté ton article à ses favoris",
  link: "/items/1",
  photo: { url: "x" },
};

describe("notifications", () => {
  it("api.vinted.fr d'abord, puis www.vinted.fr/web/gateway si la première ne répond pas", async () => {
    const faux = new FauxVinted()
      .sur("GET", /^https:\/\/api\.vinted\.fr\/inbox-notifications\/v1\/notifications\?/, () => ({
        status: 404,
        texte: "<html>Not found</html>",
      }))
      .sur("GET", /^https:\/\/www\.vinted\.fr\/web\/gateway\/inbox-notifications\/v1\/notifications\?/, () => ({
        body: { notifications: [NOTIF] },
      }));
    const r = await lireNotifications(client(faux), null);
    expect(r.source).toBe("www");
    expect(r.notifications).toEqual([{ id: "n1", body: NOTIF.body, link: "/items/1" }]); // sans la photo
  });

  it("source mémorisée essayée en premier ; 403 : arrêt sans autre essai", async () => {
    const faux = new FauxVinted().sur("GET", /web\/gateway\/inbox-notifications/, () => ({ status: 403, body: {} }));
    const err = (await lireNotifications(client(faux), "www").catch((e: unknown) => e)) as ErreurVinted;
    expect(err.arret).toBe(true);
    expect(faux.appels).toHaveLength(1);
  });
});

describe("relance d'un favori", () => {
  it("lit la transaction de la conversation, envoie le message puis l'offre", async () => {
    const faux = new FauxVinted();
    const attendre = vi.fn(async () => undefined);
    const r = await relancer(
      { conversation_id: "01a16aa3-daff-79bb-a570-c156d97cb288", texte: "Hello !", montant: "20" },
      { client: client(faux), vintedUserId: 3201823662, attendre, aleatoire: () => 0.5 },
    );
    expect(r).toMatchObject({ transaction_id: "23517428140", offre_envoyee: true, offer_id: 38066597320 });
    expect(faux.ecritures().map((a) => a.url.replace(/^https:\/\/[^/]+/, ""))).toEqual([
      "/messaging/main/conversations/01a16aa3-daff-79bb-a570-c156d97cb288/replies",
      "/api/v2/transactions/23517428140/offers",
    ]);
    expect(attendre).toHaveBeenCalledWith(3500);
  });

  it("offre refusée par Vinted après le message : erreur explicite", async () => {
    const faux = new FauxVinted().sur("POST", /\/offers$/, () => ({ status: 422, body: { message: "Prix invalide" } }));
    const err = (await relancer(
      { conversation_id: "c-1", texte: "Hello", montant: "20" },
      { client: client(faux), vintedUserId: 3201823662, attendre: async () => undefined },
    ).catch((e: unknown) => e)) as Error;
    expect(err.message).toMatch(/^Message envoyé, mais offre non envoyée : Vinted a refusé la demande \(422\)/);
  });

  it("URL de la conversation après la redirection", () => {
    expect(conversationDepuisUrl("https://www.vinted.fr/inbox/01a1729a-df35-7e50-84fc-f46b8ec2dc6a")).toBe(
      "01a1729a-df35-7e50-84fc-f46b8ec2dc6a",
    );
    expect(conversationDepuisUrl("https://www.vinted.fr/inbox/500487891429?source=want_it")).toBe("500487891429");
    expect(conversationDepuisUrl("https://www.vinted.fr/inbox/want_it?receiver_id=1&item_id=2")).toBeNull();
    expect(urlBloquante("https://www.vinted.fr/member/signup/select_type")).toBe(true);
    expect(urlBloquante("https://www.vinted.fr/inbox/123456")).toBe(false);
  });
});
