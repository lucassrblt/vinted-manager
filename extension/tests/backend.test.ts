import { describe, expect, it } from "vitest";

import { ClientBackend, ErreurBackend } from "../src/backend";
import { FauxBackend } from "./fauxBackend";

describe("client du backend", () => {
  it("envoie le jeton dans X-Extension-Token et gère le 204", async () => {
    const faux = new FauxBackend();
    expect(await faux.client().brouillonSuivant()).toBeNull();
    expect(faux.appels[0]?.jeton).toBe("vmx_test");
  });

  it("jeton refusé et backend injoignable : messages clairs", async () => {
    const refuse = new ClientBackend(async () => new Response("{}", { status: 401 }), "http://localhost:8000", "x");
    await expect(refuse.compte()).rejects.toThrow("Jeton d'extension refusé");
    const absent = new ClientBackend(async () => Promise.reject(new TypeError("fetch failed")), "http://localhost:8000/", "x");
    const err = await absent.compte().catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ErreurBackend);
    expect((err as Error).message).toContain("injoignable");
  });

  it("photos téléchargées en binaire", async () => {
    const faux = new FauxBackend().sur("GET /photos/5", () => ({ octets: new TextEncoder().encode("jpeg").buffer }));
    const octets = await faux.client().photo(5);
    expect(new TextDecoder().decode(octets)).toBe("jpeg");
  });
});
