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

describe("surveillance de Vinted", () => {
  it("consigne de surveillance envoyée à l'onglet à chaque réveil (cadence de nuit hors heures actives)", async () => {
    const sim = environnement();
    sim.backend.compte.heures_actives = false;
    await sim.moteur.tick();
    expect(sim.contenu.messages.find((m) => m.type === "surveillance")?.payload).toEqual({ actif: true, nuit: true });
  });

  it("dressing lu au démarrage puis toutes les 30 min, transmis tel quel au backend", async () => {
    const sim = environnement({ memoire: { dernierDressing: 0 } });
    await sim.moteur.tick();
    expect(sim.contenu.messages.find((m) => m.type === "dressing")?.payload).toEqual({ user_id: 3201823662 });
    expect(sim.backend.appels.find((a) => a.chemin === "/evenements")?.corps).toEqual({
      type: "dressing",
      donnees: { items: [], complet: true, total: 0 },
    });
    expect(sim.backend.chemins()).not.toContain("GET /taches/suivante"); // une lecture lourde par réveil
    sim.avancer(29 * 60_000);
    await sim.moteur.tick();
    expect(sim.contenu.messages.filter((m) => m.type === "dressing")).toHaveLength(1);
    sim.avancer(60_000);
    await sim.moteur.tick();
    expect(sim.contenu.messages.filter((m) => m.type === "dressing")).toHaveLength(2);
  });

  it("compteurs en hausse : messagerie lue, conversations demandées par le backend transmises", async () => {
    const sim = environnement();
    sim.backend.aLire = ["c1", "c2"];
    await sim.moteur.compteurs({ messages: 3, notifications: 0 });
    await sim.moteur.tick();
    const evenements = sim.backend.appels.filter((a) => a.chemin === "/evenements").map((a) => a.corps);
    expect(evenements).toEqual([
      { type: "inbox", donnees: { conversations: [] } },
      { type: "conversation", donnees: { id: "c1", messages: [] } },
      { type: "conversation", donnees: { id: "c2", messages: [] } },
    ]);
    expect(sim.attentes).toEqual([3000, 3000]); // 2 à 4 s entre deux lectures
    expect(sim.backend.chemins()).toContain("GET /taches/suivante");
  });

  it("messagerie relue toutes les 5 min même sans compteur, sauf si l'assistant est coupé", async () => {
    const sim = environnement();
    sim.avancer(5 * 60_000);
    await sim.moteur.tick();
    expect(sim.contenu.messages.filter((m) => m.type === "inbox")).toHaveLength(1);
    sim.backend.compte.modules = { ...sim.backend.compte.modules, assistant: false };
    sim.avancer(5 * 60_000);
    await sim.moteur.tick();
    expect(sim.contenu.messages.filter((m) => m.type === "inbox")).toHaveLength(1);
  });

  it("compte en pause : aucune lecture de Vinted", async () => {
    const sim = environnement({ memoire: { dernierDressing: 0, derniereInbox: 0 } });
    sim.backend.compte.pause = true;
    await sim.moteur.tick();
    expect(sim.contenu.messages.map((m) => m.type)).toEqual(["compte"]);
  });

  it("erreur 403 pendant une lecture : arrêt du compte", async () => {
    const sim = environnement({ memoire: { derniereInbox: 0 } });
    sim.contenu.inbox = () => ({
      ok: false,
      erreur: "Vinted a refusé l'accès (403)",
      arret: true,
      mauvais_compte: false,
    });
    await sim.moteur.tick();
    expect(sim.backend.chemins()).toContain("POST /arret");
    expect(sim.backend.chemins()).not.toContain("GET /taches/suivante");
  });

  it("captcha signalé par les compteurs : arrêt", async () => {
    const sim = environnement();
    await sim.moteur.compteurs({ messages: null, notifications: null, erreur: "Captcha Vinted détecté", arret: true });
    expect(sim.backend.chemins()).toEqual(["GET /compte", "POST /arret"]);
    expect(sim.memoire().inboxDemandee).toBe(true);
  });
});
