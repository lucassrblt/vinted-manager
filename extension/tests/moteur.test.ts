import { describe, expect, it, vi } from "vitest";

import { environnement } from "./simulation";

describe("service worker", () => {
  it("non configuré : rien n'est appelé", async () => {
    const sim = environnement({ configure: false });
    await sim.moteur.tick();
    expect(sim.etat.statut).toBe("non_configure");
  });

  it("onglet Vinted fermé : signal de vie seulement, aucune action", async () => {
    const sim = environnement({ onglet: null });
    await sim.moteur.tick();
    expect(sim.etat.statut).toBe("onglet_ferme");
    expect(sim.backend.chemins()).toEqual(["POST /heartbeat"]);
    expect(sim.backend.appels[0]?.corps).toEqual({ vinted_user_id: null, login: null, version: "0.1.0" });
  });

  it("signal de vie chaque minute avec le compte vu dans l'onglet", async () => {
    const sim = environnement();
    await sim.moteur.tick();
    expect(sim.backend.appels[0]).toMatchObject({
      chemin: "/heartbeat",
      corps: { vinted_user_id: 3201823662, login: "jeanmekloul" },
      jeton: "vmx_test",
    });
    sim.avancer(30_000);
    await sim.moteur.tick();
    expect(sim.backend.chemins().filter((c) => c === "POST /heartbeat")).toHaveLength(1);
    sim.avancer(30_000);
    await sim.moteur.tick();
    expect(sim.backend.chemins().filter((c) => c === "POST /heartbeat")).toHaveLength(2);
    expect(sim.etat.vinted_login).toBe("jeanmekloul");
  });

  it("demande un brouillon au plus toutes les 5 min, plus 0 à 120 s", async () => {
    const sim = environnement({ aleatoire: 0.5 });
    const demandes = () => sim.backend.chemins().filter((c) => c === "GET /brouillons/suivant").length;
    await sim.moteur.tick();
    expect(demandes()).toBe(1);
    for (let i = 0; i < 11; i++) {
      sim.avancer(30_000); // 5 min 30 s au total
      await sim.moteur.tick();
    }
    expect(demandes()).toBe(1); // 5 min + 60 s pas encore écoulées
    sim.avancer(30_000);
    await sim.moteur.tick();
    expect(demandes()).toBe(2);
  });

  it("compte en pause : aucune action", async () => {
    const sim = environnement();
    sim.backend.compte.pause = true;
    await sim.moteur.tick();
    expect(sim.backend.chemins()).not.toContain("GET /brouillons/suivant");
    expect(sim.etat.statut).toBe("pause");
  });

  it("session expirée vue au signal de vie : arrêt du compte, une seule fois", async () => {
    const sim = environnement();
    sim.contenu.compte = () => ({ ok: false, erreur: "Session Vinted expirée (401)", arret: true, mauvais_compte: false });
    await sim.moteur.tick();
    expect(sim.backend.chemins()).toEqual(["POST /heartbeat", "POST /arret"]);
    sim.avancer(60_000);
    await sim.moteur.tick();
    expect(sim.backend.chemins().filter((c) => c === "POST /arret")).toHaveLength(1);
  });

  it("brouillon réussi : résultat envoyé au backend", async () => {
    const sim = environnement();
    sim.backend.sur("GET /brouillons/suivant", () => ({ body: { article_id: 42, titre: "T-shirt", photos: [] } }));
    sim.backend.sur("POST /brouillons/42/resultat", () => ({ status: 204 }));
    sim.contenu.brouillon = vi.fn(() => ({ ok: true as const, resultat: { vinted_draft_id: 999, ai_photo: true } }));
    await sim.moteur.tick();
    expect(sim.contenu.brouillon).toHaveBeenCalledWith(expect.objectContaining({ vinted_user_id: 3201823662 }));
    expect(sim.backend.appels.at(-1)).toMatchObject({
      chemin: "/brouillons/42/resultat",
      corps: { ok: true, vinted_draft_id: 999, ai_photo: true },
    });
    expect(sim.etat.derniere_action?.texte).toBe("Brouillon créé : T-shirt");
  });

  it("réponse 403 pendant le brouillon : résultat en erreur avec arrêt, aucune nouvelle tentative", async () => {
    const sim = environnement();
    sim.backend.sur("GET /brouillons/suivant", () => ({ body: { article_id: 42, titre: "T-shirt", photos: [] } }));
    sim.backend.sur("POST /brouillons/42/resultat", () => ({ status: 204 }));
    sim.contenu.brouillon = vi.fn(() => ({ ok: false as const, erreur: "Vinted a refusé l'accès (403)", arret: true, mauvais_compte: false }));
    await sim.moteur.tick();
    expect(sim.backend.appels.at(-1)?.corps).toEqual({ ok: false, erreur: "Vinted a refusé l'accès (403)", arret: true });
    expect(sim.contenu.brouillon).toHaveBeenCalledTimes(1);
  });
});

