import { describe, expect, it, vi } from "vitest";

import { type ChargeBrouillon, creerBrouillon } from "../src/vinted/brouillon";
import { ClientVinted } from "../src/vinted/client";
import { choisirCouleurs, choisirMarque, couleursDeLaFiche, trouverTaille } from "../src/vinted/correspondances";
import { ErreurAction, ErreurVinted } from "../src/vinted/erreurs";
import { FauxVinted, capture } from "./fauxVinted";

const brouillonCapture = capture("drafts_create").request.json as {
  draft: { assigned_photos: { id: number }[]; temp_uuid: string };
};
const SESSION = brouillonCapture.draft.temp_uuid;

// Même article que la capture du 25/10 : T-shirt Nike ACG, taille M, neuf avec étiquette, 24 €.
function charge(modifs: Partial<ChargeBrouillon> = {}): ChargeBrouillon {
  return {
    article_id: 7,
    titre: "titre",
    description: "description",
    prix: "24",
    marque: "Nike ACG",
    taille: "M",
    condition_id: 6,
    couleur: "violet",
    matiere: "100% coton",
    categorie: "T-shirt",
    package_size_id: 1,
    ai_photo: false,
    photos: [11, 12, 13, 14, 15].map((photo_id, i) => ({ photo_id, type: ["devant", "dos", "etiquette", "logo", "detail"][i]! })),
    ...modifs,
  };
}

function fauxAvecPhotos(): FauxVinted {
  const faux = new FauxVinted();
  let n = 0;
  const ids = brouillonCapture.draft.assigned_photos.map((p) => p.id);
  const base = capture("photos_upload").response.body as Record<string, unknown>;
  return faux.sur("POST", /\/api\/v2\/photos$/, () => ({ body: { ...base, id: ids[n++] } }));
}

function dependances(faux: FauxVinted, vintedUserId: number | null = 3201823662) {
  return {
    client: new ClientVinted(faux.fetch, { csrf: "c", anonId: "a", siid: null }),
    photo: vi.fn(async (id: number) => new Blob([`jpeg-${id}`], { type: "image/jpeg" })),
    attendre: vi.fn(async () => undefined),
    aleatoire: () => 0.5,
    vintedUserId,
    session: SESSION,
  };
}

describe("création d'un brouillon", () => {
  it("reproduit exactement le brouillon capturé sur le site", async () => {
    const faux = fauxAvecPhotos();
    const d = dependances(faux);
    const resultat = await creerBrouillon(charge(), d);
    expect(resultat).toEqual({ vinted_draft_id: 10522041322, ai_photo: false, catalog_id: 1806, marque: "Nike ACG" });
    const creation = faux.appels.find((a) => a.url.endsWith("/item_upload/drafts"));
    expect(creation?.corps).toEqual(brouillonCapture);
  });

  it("contrôle le compte d'abord, puis envoie les photos dans l'ordre, 2 à 5 s entre chaque", async () => {
    const faux = fauxAvecPhotos();
    const d = dependances(faux);
    await creerBrouillon(charge(), d);
    expect(faux.appels[0]?.url).toContain("/users/current");
    expect(d.photo.mock.calls.map((c) => c[0])).toEqual([11, 12, 13, 14, 15]);
    expect(d.attendre).toHaveBeenCalledTimes(4);
    for (const [ms] of d.attendre.mock.calls as unknown as [number][]) {
      expect(ms).toBeGreaterThanOrEqual(2000);
      expect(ms).toBeLessThanOrEqual(5000);
    }
    const uploads = faux.appels.filter((a) => a.url.endsWith("/api/v2/photos"));
    expect(uploads).toHaveLength(5);
    expect(uploads[0]?.corps).toEqual({ "photo[type]": "item", "photo[file]": "<fichier>", "photo[temp_uuid]": SESSION });
  });

  it("déclare ai_photo et les métadonnées de chaque photo", async () => {
    const faux = fauxAvecPhotos();
    const r = await creerBrouillon(charge({ ai_photo: true }), dependances(faux));
    expect(r.ai_photo).toBe(true);
    const corps = faux.appels.find((a) => a.url.endsWith("/item_upload/drafts"))?.corps as {
      draft: { ai_photo: boolean; assigned_photos: Record<string, unknown>[] };
    };
    expect(corps.draft.ai_photo).toBe(true);
    expect(corps.draft.assigned_photos[0]).toEqual({
      id: 36532004066,
      orientation: 0,
      ai_detected: false,
      digital_source_type: [],
      c2pa_read_error: "other",
    });
  });

  it("mauvais compte connecté : aucune écriture sur Vinted", async () => {
    const faux = fauxAvecPhotos();
    const err = await creerBrouillon(charge(), dependances(faux, 3209999999)).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ErreurAction);
    expect((err as ErreurAction).mauvaisCompte).toBe(true);
    expect(faux.ecritures()).toHaveLength(0);
  });

  it("taille introuvable : erreur claire, pas de brouillon", async () => {
    const faux = fauxAvecPhotos();
    const err = (await creerBrouillon(charge({ taille: "W32" }), dependances(faux)).catch((e: unknown) => e)) as Error;
    expect(err.message).toBe("Taille introuvable : « W32 » n'existe pas dans cette catégorie Vinted.");
    expect(faux.appels.some((a) => a.url.endsWith("/item_upload/drafts"))).toBe(false);
  });

  it("marque inconnue de Vinted : erreur, jamais une autre marque", async () => {
    const faux = fauxAvecPhotos();
    const err = (await creerBrouillon(charge({ marque: "Marque Inventée" }), dependances(faux)).catch((e: unknown) => e)) as Error;
    expect(err.message).toBe("Marque introuvable sur Vinted : « Marque Inventée ».");
    expect(faux.appels.some((a) => a.url.includes("/item_upload/brands?category_id=1806"))).toBe(true);
  });

  it("une réponse 403 pendant l'envoi des photos arrête tout", async () => {
    const faux = fauxAvecPhotos().sur("POST", /\/api\/v2\/photos$/, () => ({ status: 403, body: {} }));
    const err = (await creerBrouillon(charge(), dependances(faux)).catch((e: unknown) => e)) as ErreurVinted;
    expect(err).toBeInstanceOf(ErreurVinted);
    expect(err.arret).toBe(true);
    expect(faux.ecritures()).toHaveLength(1); // une seule tentative, rien après
  });

  it("taille d'un sweat (catégorie 268)", async () => {
    const faux = fauxAvecPhotos().sur("POST", /suggestions\/categories$/, () => ({
      body: { prefill_categories: [268], code: 0 },
    }));
    const r = await creerBrouillon(charge({ taille: "L", package_size_id: 2 }), dependances(faux));
    expect(r.catalog_id).toBe(268);
    const corps = faux.appels.find((a) => a.url.endsWith("/item_upload/drafts"))?.corps as {
      draft: { item_attributes: { code: string; ids: number[] }[]; package_size_id: number };
    };
    expect(corps.draft.item_attributes[0]).toEqual({ code: "size", ids: [209] });
    expect(corps.draft.package_size_id).toBe(2);
  });
});

describe("correspondances", () => {
  const attributs = (capture("attributes_1806").response.body as { attributes: never[] }).attributes;
  const couleurs = (capture("colors").response.body as { colors: { id: number; title: string }[] }).colors;

  it("tailles", () => {
    expect(trouverTaille(attributs, "M")).toBe(208);
    expect(trouverTaille(attributs, "taille xl")).toBe(210);
    expect(trouverTaille(attributs, "TU")).toBe(213);
    expect(() => trouverTaille(attributs, null)).toThrow("Taille manquante");
  });

  it("marque : la fiche prime, la suggestion seulement si la fiche est vide", () => {
    const suggestions = { brands: [{ id: 687713, title: "Nike ACG" }, { id: 53, title: "Nike" }], prefill_brand: { id: 687713, title: "Nike ACG" } };
    expect(choisirMarque("Nike", suggestions, null)).toEqual({ id: 53, title: "Nike" });
    expect(choisirMarque(null, suggestions, null)).toEqual({ id: 687713, title: "Nike ACG" });
    expect(choisirMarque("nike-acg", suggestions, null).id).toBe(687713);
    expect(() => choisirMarque("Adidas", suggestions, [])).toThrow("Marque introuvable");
  });

  it("couleurs : suggestion de Vinted, sinon la fiche", () => {
    expect(choisirCouleurs("violet", { dynamic_attributes: [{ code: "color", suggested_option_ids: ["25"] }] }, couleurs)).toEqual([25]);
    expect(couleursDeLaFiche("bleu marine", couleurs)).toEqual([27]);
    expect(couleursDeLaFiche("Gris chiné", couleurs)).toEqual([3]);
    expect(couleursDeLaFiche("violet", couleurs)).toEqual([6]);
    expect(couleursDeLaFiche("multicolore", couleurs)).toEqual([15]);
    expect(couleursDeLaFiche("à pois", couleurs)).toEqual([]);
  });
});
