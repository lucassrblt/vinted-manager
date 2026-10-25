import { describe, expect, it } from "vitest";

import { API, ClientVinted, WWW, lireContexte } from "../src/vinted/client";
import { ErreurVinted } from "../src/vinted/erreurs";
import { FauxVinted, capture, toutesLesCaptures } from "./fauxVinted";

const contexte = { csrf: "csrf-test", anonId: "anon-test", siid: null };

describe("captures", () => {
  it("toutes les captures fournies sont présentes et sans jeton", () => {
    const noms = toutesLesCaptures();
    expect(noms).toHaveLength(26);
    for (const nom of noms) {
      const texte = JSON.stringify(capture(nom));
      expect(texte).not.toMatch(/"(access_token|refresh_token|_vinted_fr_session|cookie)"/i);
    }
  });
});

describe("ClientVinted", () => {
  it("envoie les en-têtes du site et les cookies du navigateur", async () => {
    const faux = new FauxVinted();
    const client = new ClientVinted(faux.fetch, contexte);
    await client.utilisateurCourant();
    await client.nonLusMessages();
    const [www, api] = faux.appels;
    expect(www?.url).toBe(`${WWW}/api/v2/users/current`);
    expect(www?.credentials).toBe("include");
    expect(www?.entetes).toMatchObject({ "x-csrf-token": "csrf-test", "x-anon-id": "anon-test", locale: "fr-FR" });
    expect(www?.entetes).not.toHaveProperty("platform");
    expect(api?.url).toBe(`${API}/messaging/main/users/unread_count`);
    expect(api?.entetes).toMatchObject({ platform: "web", "x-next-app": "marketplace-web" });
    expect(api?.entetes).not.toHaveProperty("siid"); // absent de la page : pas envoyé
  });

  it.each([
    [401, true, "Session Vinted expirée"],
    [403, true, "403"],
    [429, true, "429"],
  ])("réponse %i : arrêt du compte", async (statut, arret, message) => {
    const faux = new FauxVinted().sur("GET", /users\/current/, () => ({ status: statut, body: {} }));
    const err = await new ClientVinted(faux.fetch, contexte).utilisateurCourant().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ErreurVinted);
    expect((err as ErreurVinted).arret).toBe(arret);
    expect((err as ErreurVinted).message).toContain(message);
  });

  it("une page HTML (captcha) ou non JSON arrête le compte", async () => {
    const faux = new FauxVinted().sur("GET", /users\/current/, () => ({
      status: 200,
      texte: "<html><title>Captcha</title><script src='https://ct.captcha-delivery.com/c.js'></script></html>",
    }));
    const err = (await new ClientVinted(faux.fetch, contexte).utilisateurCourant().catch((e: unknown) => e)) as ErreurVinted;
    expect(err.arret).toBe(true);
    expect(err.message).toContain("Captcha");
    faux.sur("GET", /users\/current/, () => ({ status: 502, texte: "Bad gateway" }));
    const err2 = (await new ClientVinted(faux.fetch, contexte).utilisateurCourant().catch((e: unknown) => e)) as ErreurVinted;
    expect(err2.arret).toBe(true);
    expect(err2.message).toContain("non JSON");
  });

  it("un défi DataDome en JSON arrête le compte", async () => {
    const faux = new FauxVinted().sur("GET", /users\/current/, () => ({
      status: 200,
      body: { url: "https://geo.captcha-delivery.com/captcha/?initialCid=x" },
    }));
    const err = (await new ClientVinted(faux.fetch, contexte).utilisateurCourant().catch((e: unknown) => e)) as ErreurVinted;
    expect(err.arret).toBe(true);
  });

  it("un refus JSON (validation) est une erreur simple, sans arrêt", async () => {
    const faux = new FauxVinted().sur("POST", /item_upload\/drafts$/, () => ({
      status: 422,
      body: { code: 99, message: "Le prix est invalide" },
    }));
    const client = new ClientVinted(faux.fetch, contexte);
    const err = (await client.creerBrouillon({} as never, "s").catch((e: unknown) => e)) as ErreurVinted;
    expect(err.arret).toBe(false);
    expect(err.message).toContain("Le prix est invalide");
  });

  it("aucune nouvelle tentative après un échec", async () => {
    const faux = new FauxVinted().sur("POST", /item_upload\/drafts$/, () => ({ status: 500, body: { message: "erreur" } }));
    await new ClientVinted(faux.fetch, contexte).creerBrouillon({} as never, "s").catch(() => undefined);
    expect(faux.ecritures()).toHaveLength(1);
  });

  it("lit le jeton CSRF, l'anon_id et le siid dans la page", () => {
    const doc = {
      querySelector: () => null,
      documentElement: { innerHTML: '{\\"CSRF_TOKEN\\":\\"abc-123\\",\\"siid\\":\\"0f8c1e2a-1111-4222-8333-444455556666\\"}' },
      cookie: "v_udt=x; anon_id=9a8b%2Dc; autre=1",
    } as unknown as Document;
    expect(lireContexte(doc)).toEqual({ csrf: "abc-123", anonId: "9a8b-c", siid: "0f8c1e2a-1111-4222-8333-444455556666" });
    const meta = { ...doc, querySelector: () => ({ getAttribute: () => "meta-csrf" }), documentElement: { innerHTML: "" } };
    expect(lireContexte(meta as unknown as Document).csrf).toBe("meta-csrf");
  });
});
