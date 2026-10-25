import { describe, expect, it, vi } from "vitest";

import { environnement } from "./simulation";

const TACHE = { id: 42, type: "brouillon", article_id: 7, payload: { titre: "T-shirt" } };

describe("service worker", () => {
  it("non configuré : rien n'est appelé", async () => {
    const sim = environnement({ configure: false });
    await sim.moteur.tick();
    expect(sim.etat.statut).toBe("non_configure");
  });

  it("onglet Vinted fermé : signal de vie (onglet absent) seulement, aucune action", async () => {
    const sim = environnement({ onglet: null });
    await sim.moteur.tick();
    expect(sim.etat.statut).toBe("onglet_ferme");
    expect(sim.backend.chemins()).toEqual(["POST /heartbeat"]);
    expect(sim.backend.appels[0]?.corps).toEqual({
      vinted_user_id: null,
      login: null,
      version: "0.1.0",
      onglet: false,
    });
  });

  it("signal de vie chaque minute avec le compte vu dans l'onglet", async () => {
    const sim = environnement();
    await sim.moteur.tick();
    expect(sim.backend.appels[0]).toMatchObject({
      chemin: "/heartbeat",
      corps: { vinted_user_id: 3201823662, login: "jeanmekloul", onglet: true },
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

  it("demande la tâche suivante à chaque réveil", async () => {
    const sim = environnement();
    await sim.moteur.tick();
    sim.avancer(30_000);
    await sim.moteur.tick();
    expect(sim.backend.chemins().filter((c) => c === "GET /taches/suivante")).toHaveLength(2);
  });

  it("compte en pause ou automatisation coupée : aucune action", async () => {
    const sim = environnement();
    sim.backend.compte.pause = true;
    await sim.moteur.tick();
    expect(sim.backend.chemins()).not.toContain("GET /taches/suivante");
    expect(sim.etat.statut).toBe("pause");
    sim.backend.compte = { ...sim.backend.compte, pause: false, automatisation_active: false };
    sim.avancer(60_000);
    await sim.moteur.tick();
    expect(sim.backend.chemins()).not.toContain("GET /taches/suivante");
  });

  it("session expirée vue au signal de vie : arrêt du compte, une seule fois", async () => {
    const sim = environnement();
    sim.contenu.compte = () => ({
      ok: false,
      erreur: "Session Vinted expirée (401)",
      arret: true,
      mauvais_compte: false,
    });
    await sim.moteur.tick();
    expect(sim.backend.chemins()).toEqual(["POST /heartbeat", "POST /arret"]);
    sim.avancer(60_000);
    await sim.moteur.tick();
    expect(sim.backend.chemins().filter((c) => c === "POST /arret")).toHaveLength(1);
  });

  it("tâche réussie : résultat envoyé au backend", async () => {
    const sim = environnement();
    sim.backend.sur("GET /taches/suivante", () => ({ body: TACHE }));
    sim.contenu.executer = vi.fn(() => ({ ok: true as const, resultat: { vinted_draft_id: 999, ai_photo: true } }));
    await sim.moteur.tick();
    expect(sim.contenu.executer).toHaveBeenCalledWith({ tache: TACHE, vinted_user_id: 3201823662 });
    expect(sim.backend.appels.at(-1)).toMatchObject({
      chemin: "/taches/42/resultat",
      corps: { ok: true, resultat: { vinted_draft_id: 999, ai_photo: true } },
    });
    expect(sim.etat.derniere_action?.texte).toBe("Brouillon : fait");
  });

  it("réponse 403 : résultat en erreur avec arrêt, aucune nouvelle tentative", async () => {
    const sim = environnement();
    sim.backend.sur("GET /taches/suivante", () => ({ body: TACHE }));
    sim.contenu.executer = vi.fn(() => ({
      ok: false as const,
      erreur: "Vinted a refusé l'accès (403)",
      arret: true,
      mauvais_compte: false,
      erreur_vinted: true,
    }));
    await sim.moteur.tick();
    expect(sim.backend.appels.at(-1)?.corps).toEqual({
      ok: false,
      erreur: "Vinted a refusé l'accès (403)",
      arret: true,
      erreur_vinted: true,
    });
    expect(sim.contenu.executer).toHaveBeenCalledTimes(1);
  });
});
