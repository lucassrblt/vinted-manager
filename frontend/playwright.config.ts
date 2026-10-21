import { defineConfig } from "@playwright/test";

// Prérequis : backend + frontend lancés (docker compose up), base vide, utilisateur créé.
// E2E_EMAIL / E2E_MOT_DE_PASSE / E2E_EXCEL configurent le parcours.
export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  use: { baseURL: process.env.E2E_URL ?? "http://localhost:3000", locale: "fr-FR", timezoneId: "Europe/Paris" },
});
