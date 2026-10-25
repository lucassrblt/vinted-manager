import { describe, expect, it, vi } from "vitest";

import { ClientVinted } from "../src/vinted/client";
import { executer, fetchParLaPage, serialiser } from "../src/vinted/pont";
import { FauxVinted } from "./fauxVinted";

/** Content script et pont reliés comme par window.postMessage. */
function relies(fetchPage: typeof fetch) {
  const ecouteurs = new Set<(d: unknown) => void>();
  const diffuser = (d: unknown) => ecouteurs.forEach((e) => e(structuredClone(d)));
  const page = vi.fn(fetchPage);
  const fetchContenu = fetchParLaPage(
    (message) => {
      diffuser(message);
      const m = message as { source: string; id: string; requete: Parameters<typeof executer>[0] };
      if (m.source === "vinted-manager:contenu") {
        void executer(m.requete, page).then((reponse) =>
          diffuser({ source: "vinted-manager:pont", id: m.id, reponse }),
        );
      }
    },
    (rappel) => {
      ecouteurs.add(rappel);
      return () => ecouteurs.delete(rappel);
    },
  );
  return { fetchContenu, page };
}

describe("pont vers le contexte de la page", () => {
  it("les appels passent par le fetch de la page, avec les mêmes en-têtes", async () => {
    const faux = new FauxVinted();
    const { fetchContenu, page } = relies(faux.fetch as unknown as typeof fetch);
    const client = new ClientVinted(fetchContenu, { csrf: "c", anonId: "a", siid: null });
    expect(await client.utilisateurCourant()).toEqual({ user: { id: 3201823662, login: "jeanmekloul" } });
    expect(page).toHaveBeenCalledTimes(1);
    expect(faux.appels[0]?.entetes).toMatchObject({ "x-csrf-token": "c", "x-anon-id": "a" });
    expect(faux.appels[0]?.credentials).toBe("include");
  });

  it("formulaire d'envoi de photo reconstruit de l'autre côté", async () => {
    const faux = new FauxVinted();
    const { fetchContenu } = relies(faux.fetch as unknown as typeof fetch);
    const client = new ClientVinted(fetchContenu, { csrf: "c", anonId: "a", siid: null });
    const r = await client.envoyerPhoto(new Blob(["jpeg"], { type: "image/jpeg" }), "uuid-1");
    expect(r.id).toBe(36532004066);
    expect(faux.appels[0]?.corps).toEqual({
      "photo[type]": "item",
      "photo[file]": "<fichier>",
      "photo[temp_uuid]": "uuid-1",
    });
  });

  it("le pont refuse toute adresse hors de Vinted", async () => {
    const page = vi.fn();
    expect(await executer(serialiser("https://exemple.com/x", {}), page)).toEqual({
      ok: false,
      erreur: "Adresse refusée : https://exemple.com/x",
    });
    expect(page).not.toHaveBeenCalled();
  });

  it("pont absent : erreur réseau après le délai, sans arrêt du compte", async () => {
    vi.useFakeTimers();
    const f = fetchParLaPage(
      () => undefined,
      () => () => undefined,
      1000,
    );
    const promesse = f("https://www.vinted.fr/api/v2/users/current", {}).catch((e: unknown) => e);
    vi.advanceTimersByTime(1000);
    expect(String(await promesse)).toContain("pont de la page Vinted ne répond pas");
    vi.useRealTimers();
  });
});
