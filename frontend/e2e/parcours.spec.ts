import { expect, test } from "@playwright/test";

// Prérequis : backend lancé avec IA_FACTICE=true (aucun appel réseau à l'IA), base vide,
// utilisateur E2E_EMAIL / E2E_MOT_DE_PASSE créé (python -m app.cli create-user).
const EMAIL = process.env.E2E_EMAIL ?? "demo@example.com";
const MOT_DE_PASSE = process.env.E2E_MOT_DE_PASSE ?? "demo-motdepasse";
const EXCEL = process.env.E2E_EXCEL ?? "../backend/tests/data/suivi-revente.xlsx";

test("connexion → import → création d'annonce → marquer publié", async ({ page }) => {
  await page.goto("/stock");
  await expect(page).toHaveURL(/\/login/);
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Mot de passe").fill(MOT_DE_PASSE);
  await page.getByRole("button", { name: "Se connecter" }).click();
  await expect(page).toHaveURL(/\/stock$/);

  // Import de l'Excel
  await page.goto("/import");
  await page.setInputFiles("input[type=file]", EXCEL);
  await expect(page.getByRole("button", { name: "Valider l'import" })).toBeEnabled();
  await page.getByRole("button", { name: "Valider l'import" }).click();
  await expect(page.getByText("Import terminé :")).toBeVisible();

  // Création d'annonce sur le premier article à publier
  await page.goto("/annonces");
  const premier = page.locator("ul li a").first();
  const nom = (await premier.locator("span.font-medium").textContent())?.trim() ?? "";
  await premier.click();
  await page.getByLabel("État").click();
  await page.getByRole("option", { name: "Très bon état" }).click();
  await page.getByRole("button", { name: "Générer l'annonce" }).click();
  await expect(page.getByLabel("Titre", { exact: true })).not.toHaveValue("");
  await expect(page.getByLabel("Description")).toHaveValue(/lot/);

  // Publication
  await page.getByLabel("Prix de mise en ligne (€)").fill("45");
  await page.getByRole("button", { name: "Marquer comme publié" }).click();
  await expect(page).toHaveURL(/\/annonces$/);
  await expect(page.getByText(nom, { exact: true })).toHaveCount(0);

  // L'article est en ligne dans le stock, avec sa date de publication
  await page.goto("/stock");
  await page.getByPlaceholder("Rechercher un article…").fill(nom.slice(0, 25));
  await expect(page.locator("table").getByText("En ligne").first()).toBeVisible();
});
