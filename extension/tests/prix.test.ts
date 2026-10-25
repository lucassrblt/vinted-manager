import { describe, expect, it } from "vitest";

import { ClientVinted } from "../src/vinted/client";
import { ErreurAction } from "../src/vinted/erreurs";
import { modifierPrix, reconstruireItem } from "../src/vinted/prix";
import { FauxVinted, capture } from "./fauxVinted";

// Capture du PUT fait par le site (modification du prix d'une annonce) : c'est l'objet à reproduire.
const PUT = capture("items_update").request.json as { item: Record<string, unknown> };
const ITEM_ID = 10495425715;

/** Annonce telle que GET /api/v2/items/{id} pourrait la renvoyer (synthétique : pas de capture). */
function annonceLue(modifs: Record<string, unknown> = {}): Record<string, unknown> {
  const it = PUT.item;
  return {
    id: it.id,
    title: it.title,
    description: it.description,
    brand_dto: { id: it.brand_id, title: it.brand },
    catalog_id: it.catalog_id,
    price: { amount: "22.0", currency_code: "EUR" },
    currency: "EUR",
    package_size_id: it.package_size_id,
    color1_id: 25,
    color2_id: null,
    photos: (it.assigned_photos as { id: number }[]).map((p) => ({ id: p.id, url: "https://images1.vinted.net/x" })),
    item_attributes: it.item_attributes,
    isbn: null,
    measurement_length: null,
    measurement_width: null,
    is_closed: false,
    ...modifs,
  };
}

function client(faux: FauxVinted) {
  return new ClientVinted(faux.fetch, { csrf: "c", anonId: "a", siid: null });
}

describe("reconstruction de l'objet item", () => {
  it("identique à la capture du site, au prix et au temp_uuid près", () => {
    const item = reconstruireItem(annonceLue(), "20.5", false, "nouvelle-session");
    expect(item).toEqual({ ...PUT.item, price: "20.5", temp_uuid: "nouvelle-session" });
  });

  it("champ manquant : rien n'est reconstruit", () => {
    const sansAttributs = annonceLue({ item_attributes: undefined, brand_dto: undefined });
    expect(() => reconstruireItem(sansAttributs, "20", false, "s")).toThrow(
      "Champ manquant dans l'annonce lue : brand_id, brand, item_attributes.",
    );
    expect(() => reconstruireItem(annonceLue(), "20", null, "s")).toThrow("ai_photo");
  });
});

describe("baisse de prix", () => {
  const tache = { item_id: ITEM_ID, prix_actuel: "22", nouveau_prix: "21", ai_photo: false };

  it("relit l'annonce puis envoie l'objet complet", async () => {
    const faux = new FauxVinted().sur("GET", /\/api\/v2\/items\/\d+\?/, () => ({ body: { item: annonceLue() } }));
    const r = await modifierPrix(tache, { client: client(faux), vintedUserId: 3201823662 });
    expect(r).toEqual({ item_id: ITEM_ID, prix: "21" });
    const put = faux.ecritures()[0];
    expect(put?.methode).toBe("PUT");
    expect(put?.url).toBe(`https://www.vinted.fr/api/v2/item_upload/items/${ITEM_ID}`);
    const corps = put?.corps as { item: Record<string, unknown>; push_up: boolean; upload_session_id: string };
    expect(corps.push_up).toBe(false);
    expect(corps.item.price).toBe("21");
    expect(corps.item.temp_uuid).toBe(corps.upload_session_id);
    expect(Object.keys(corps.item).sort()).toEqual(Object.keys(PUT.item).sort());
  });

  it("champs manquants dans la lecture réelle : aucun PUT", async () => {
    const faux = new FauxVinted(); // lecture synthétique minimale : pas d'item_attributes
    const err = await modifierPrix(tache, { client: client(faux), vintedUserId: 3201823662 }).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ErreurAction);
    expect((err as Error).message).toMatch(/^Champ manquant/);
    expect(faux.ecritures()).toHaveLength(0);
  });

  it("prix changé à la main entre-temps : rien n'est modifié", async () => {
    const faux = new FauxVinted().sur("GET", /\/api\/v2\/items\/\d+\?/, () => ({
      body: { item: annonceLue({ price: { amount: "19.0" } }) },
    }));
    const err = (await modifierPrix(tache, { client: client(faux), vintedUserId: 3201823662 }).catch(
      (e: unknown) => e,
    )) as Error;
    expect(err.message).toContain("Prix modifié entre-temps");
    expect(faux.ecritures()).toHaveLength(0);
  });
});
