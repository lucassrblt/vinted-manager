import { expect, test } from "@playwright/test";

const EMAIL = process.env.E2E_EMAIL ?? "demo@example.com";
const MOT_DE_PASSE = process.env.E2E_MOT_DE_PASSE ?? "demo-motdepasse";
const EXCEL = process.env.E2E_EXCEL ?? "../backend/tests/data/suivi-revente.xlsx";

// Étape 1 : connexion -> import. La suite (création d'annonce -> marquer publié) arrive à l'étape 3.
test("connexion puis import de l'Excel", async ({ page }) => {
  await page.goto("/stock");
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Mot de passe").fill(MOT_DE_PASSE);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL(/\/stock$/);

  await page.goto("/import");
  await page.setInputFiles("input[type=file]", EXCEL);
  await expect(page.getByRole("button", { name: "Valider l'import" })).toBeEnabled();
  await page.getByRole("button", { name: "Valider l'import" }).click();
  await expect(page.getByText("Import terminé :")).toBeVisible();

  await page.getByRole("link", { name: "Voir le stock" }).click();
  await expect(page.getByText("58 articles")).toBeVisible();
});
