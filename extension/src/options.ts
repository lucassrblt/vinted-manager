/** Options : URL du backend et jeton du compte. L'accès à l'URL du backend est demandé au besoin. */
import { ClientBackend } from "./backend";
import { BACKEND_DEFAUT, type Config } from "./etat";

const url = document.getElementById("url") as HTMLInputElement;
const jeton = document.getElementById("jeton") as HTMLInputElement;
const resultat = document.getElementById("resultat")!;

void chrome.storage.local.get("config").then(({ config }) => {
  const c = config as Config | undefined;
  url.value = c?.backendUrl ?? BACKEND_DEFAUT;
  jeton.value = c?.jeton ?? "";
});

document.getElementById("formulaire")!.addEventListener("submit", async (e) => {
  e.preventDefault();
  const config: Config = {
    backendUrl: (url.value.trim() || BACKEND_DEFAUT).replace(/\/+$/, ""),
    jeton: jeton.value.trim(),
  };
  let origine: string;
  try {
    origine = new URL(config.backendUrl).origin;
  } catch {
    resultat.textContent = "URL invalide.";
    return;
  }
  const accorde = await chrome.permissions.request({ origins: [`${origine}/*`] });
  if (!accorde) {
    resultat.textContent = "Accès au backend refusé : l'extension ne pourra pas le joindre.";
    return;
  }
  await chrome.storage.local.set({ config });
  try {
    const compte = await new ClientBackend((u, i) => fetch(u, i), config.backendUrl, config.jeton).compte();
    resultat.textContent = `Connecté au compte « ${compte.nom} ».`;
    void chrome.runtime.sendMessage({ type: "tick" });
  } catch (err) {
    resultat.textContent = (err as Error).message;
  }
});
