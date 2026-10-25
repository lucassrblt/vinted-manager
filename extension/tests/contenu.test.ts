import { describe, expect, it, vi } from "vitest";

import { Contenu } from "../src/contenu";
import { blobVersBase64 } from "../src/outils";
import { ClientVinted } from "../src/vinted/client";
import { FauxVinted } from "./fauxVinted";

function contenu(faux: FauxVinted, maintenant = () => 0) {
  return new Contenu({
    client: () => new ClientVinted(faux.fetch, { csrf: "c", anonId: "a", siid: null }),
    demanderPhoto: vi.fn(async () => ({
      ok: true as const,
      resultat: { base64: blobVersBase64(new TextEncoder().encode("jpeg").buffer) },
    })),
    attendre: async () => undefined,
    maintenant,
  });
}

describe("content script", () => {
  it("compte courant relu au plus toutes les 5 minutes", async () => {
    const faux = new FauxVinted();
    let t = 0;
    const c = contenu(faux, () => t);
    expect(await c.traiter({ type: "compte", id: "1", payload: null })).toEqual({
      ok: true,
      resultat: { id: 3201823662, login: "jeanmekloul" },
    });
    t = 4 * 60_000;
    await c.traiter({ type: "compte", id: "2", payload: null });
    expect(faux.appels).toHaveLength(1);
    t = 6 * 60_000;
    await c.traiter({ type: "compte", id: "3", payload: null });
    expect(faux.appels).toHaveLength(2);
  });

  it("session expirée : réponse avec arrêt", async () => {
    const faux = new FauxVinted().sur("GET", /users\/current/, () => ({ status: 401, body: {} }));
    const r = await contenu(faux).traiter({ type: "compte", id: "1", payload: null });
    expect(r).toMatchObject({ ok: false, arret: true });
  });

  it("brouillon complet depuis l'onglet, photos demandées au service worker", async () => {
    const faux = new FauxVinted();
    const c = contenu(faux);
    const r = await c.traiter({
      type: "executer",
      id: "1",
      payload: {
        vinted_user_id: 3201823662,
        tache: {
          id: 9,
          type: "brouillon",
          article_id: 1,
          payload: {
            article_id: 1,
            titre: "T-shirt Nike ACG violet taille M",
            description: "T-shirt Nike ACG violet, taille M.",
            prix: "24",
            marque: "Nike ACG",
            taille: "M",
            condition_id: 6,
            couleur: "violet",
            matiere: "coton",
            categorie: "T-shirt",
            package_size_id: 1,
            ai_photo: true,
            photos: [1, 2, 3, 4, 5].map((photo_id) => ({ photo_id, type: "detail" })),
          },
        },
      },
    });
    expect(r).toEqual({
      ok: true,
      resultat: { vinted_draft_id: 10522041322, ai_photo: true, catalog_id: 1806, marque: "Nike ACG" },
    });
  });

  it("mauvais compte connecté : erreur signalée comme telle", async () => {
    const r = await contenu(new FauxVinted()).traiter({
      type: "executer",
      id: "1",
      payload: { vinted_user_id: 1, tache: { id: 1, type: "brouillon", article_id: 1, payload: { photos: [] } } },
    });
    expect(r).toMatchObject({ ok: false, mauvais_compte: true, arret: false, erreur_vinted: false });
  });

  it("type de tâche inconnu de cette version : erreur claire", async () => {
    const r = await contenu(new FauxVinted()).traiter({
      type: "executer",
      id: "1",
      payload: { vinted_user_id: 1, tache: { id: 1, type: "inconnu", article_id: null, payload: {} } },
    });
    expect(r).toMatchObject({ ok: false, erreur: "Type de tâche non pris en charge par cette version : inconnu." });
  });
});
