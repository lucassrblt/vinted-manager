import { describe, expect, it, vi } from "vitest";

import { versReponse } from "../src/contenu";
import { ClientVinted } from "../src/vinted/client";
import { ErreurAction } from "../src/vinted/erreurs";
import { type ChargeRepublication, ErreurPartielle, republier } from "../src/vinted/republication";
import { FauxVinted, capture } from "./fauxVinted";
import { environnement } from "./simulation";

const ANCIEN = 10495425715;

const charge: ChargeRepublication = {
  ancien_item_id: ANCIEN,
  titre: "T-shirt ACG Nike violet lavande taille M",
  description: "T-shirt Nike ACG violet, taille M.\nPorté mais en très bon état.",
  prix: "22",
  marque: "Nike ACG",
  taille: "M",
  condition_id: 2,
  couleur: "violet",
  matiere: null,
  package_size_id: 1,
  ai_photo: false,
  photos: [0, 1, 2, 3, 4].map((index) => ({ index })),
};

function contexte(faux: FauxVinted) {
  return {
    client: new ClientVinted(faux.fetch, { csrf: "c", anonId: "a", siid: null }),
    vintedUserId: 3201823662,
    photo: vi.fn(async (i: number) => new Blob([`photo-${i}`], { type: "image/jpeg" })),
    attendre: vi.fn(async () => undefined),
    aleatoire: () => 0.5,
    session: "965f9442-86be-4b42-ba70-d2844206ffc6",
  };
}

describe("republication", () => {
  it("brouillon, publication, puis suppression de l'ancienne annonce, dans cet ordre", async () => {
    const faux = new FauxVinted();
    const e = contexte(faux);
    const r = await republier(charge, e);
    expect(r).toEqual({ nouvel_item_id: 10521949755, ancien_item_id: ANCIEN });
    const etapes = faux.appels.map(
      (a) => `${a.methode} ${a.url.replace(/^https:\/\/www\.vinted\.fr/, "").split("?")[0]}`,
    );
    expect(etapes[0]).toBe("GET /api/v2/users/current");
    expect(etapes[1]).toBe(`GET /api/v2/items/${ANCIEN}`);
    expect(etapes.slice(-3)).toEqual([
      "POST /api/v2/item_upload/drafts",
      "POST /api/v2/item_upload/drafts/10522041322/completion",
      `POST /api/v2/items/${ANCIEN}/delete`,
    ]);
    expect(e.photo.mock.calls.map((c) => c[0])).toEqual([0, 1, 2, 3, 4]);
    const publication = faux.appels.find((a) => a.url.endsWith("/completion"))?.corps as {
      draft: { id: number; assigned_photos: Record<string, unknown>[]; title: string };
      push_up: boolean;
    };
    expect(publication.push_up).toBe(false);
    expect(publication.draft.id).toBe(10522041322);
    expect(publication.draft.title).toBe(charge.titre);
    expect(Object.keys(publication.draft.assigned_photos[0] ?? {})).toEqual(["id", "orientation"]);
    // Forme identique à la capture de la publication d'un brouillon (mêmes champs).
    const capturee = (capture("drafts_completion").request.json as { draft: Record<string, unknown> }).draft;
    expect(Object.keys(publication.draft).sort()).toEqual(Object.keys(capturee).sort());
  });

  it("annonce vendue ou réservée entre-temps : rien n'est fait", async () => {
    const faux = new FauxVinted().sur("GET", /\/api\/v2\/items\/\d+\?/, () => ({
      body: { item: { id: ANCIEN, is_reserved: true } },
    }));
    const err = await republier(charge, contexte(faux)).catch((x: unknown) => x);
    expect(err).toBeInstanceOf(ErreurAction);
    expect(faux.ecritures()).toHaveLength(0);
  });

  it("publication refusée : l'ancienne annonce reste en ligne, le brouillon est signalé", async () => {
    const faux = new FauxVinted().sur("POST", /\/completion$/, () => ({
      status: 422,
      body: { message: "Photo refusée" },
    }));
    const err = (await republier(charge, contexte(faux)).catch((x: unknown) => x)) as ErreurPartielle;
    expect(err).toBeInstanceOf(ErreurPartielle);
    expect(err.partiel).toEqual({ brouillon_id: 10522041322 });
    expect(faux.appels.some((a) => a.url.endsWith("/delete"))).toBe(false);
    expect(versReponse(err)).toMatchObject({ ok: false, erreur_vinted: true, resultat: { brouillon_id: 10522041322 } });
  });

  it("suppression de l'ancienne refusée : la nouvelle annonce est remontée au backend", async () => {
    const faux = new FauxVinted().sur("POST", /\/delete$/, () => ({ status: 403, body: {} }));
    const err = (await republier(charge, contexte(faux)).catch((x: unknown) => x)) as ErreurPartielle;
    expect(versReponse(err)).toMatchObject({ ok: false, arret: true, resultat: { nouvel_item_id: 10521949755 } });
    expect(err.message).toContain("l'ancienne (10495425715) n'a pas été supprimée");
  });
});

describe("photos de référence d'une annonce importée", () => {
  it("téléchargées depuis le CDN de Vinted puis envoyées au backend", async () => {
    const sim = environnement();
    sim.backend.sur("GET /taches/suivante", () => ({
      body: {
        id: 70,
        type: "photos_reference",
        article_id: 9,
        payload: { urls: ["https://images1.vinted.net/a.jpg", "https://images1.vinted.net/b.jpg"] },
      },
    }));
    sim.backend.sur("POST /articles/9/photos-reference", () => ({ status: 201, body: { photos: 2 } }));
    await sim.moteur.tick();
    expect(sim.telechargements).toEqual(["https://images1.vinted.net/a.jpg", "https://images1.vinted.net/b.jpg"]);
    expect(sim.backend.chemins()).toContain("POST /articles/9/photos-reference");
    expect(sim.backend.appels.at(-1)).toMatchObject({
      chemin: "/taches/70/resultat",
      corps: { ok: true, resultat: { photos: 2 } },
    });
    expect(sim.contenu.messages.map((m) => m.type)).not.toContain("executer"); // aucun appel à l'API Vinted
  });

  it("échec partiel transmis avec le résultat déjà obtenu", async () => {
    const sim = environnement();
    sim.backend.sur("GET /taches/suivante", () => ({
      body: { id: 71, type: "republication", article_id: 9, payload: {} },
    }));
    sim.contenu.executer = () => ({
      ok: false,
      erreur: "ancienne non supprimée",
      arret: false,
      mauvais_compte: false,
      erreur_vinted: true,
      resultat: { nouvel_item_id: 42 },
    });
    await sim.moteur.tick();
    expect(sim.backend.appels.at(-1)?.corps).toEqual({
      ok: false,
      erreur: "ancienne non supprimée",
      arret: false,
      erreur_vinted: true,
      resultat: { nouvel_item_id: 42 },
    });
  });
});
