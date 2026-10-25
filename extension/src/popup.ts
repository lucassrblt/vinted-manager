/** Popup : état du compte, brouillons du jour, dernière action, Pause / Reprendre. */
import { ETAT_INITIAL, type Etat } from "./etat";

const LIBELLES: Record<Etat["statut"], string> = {
  non_configure: "à configurer",
  actif: "actif",
  pause: "en pause",
  erreur: "erreur",
  onglet_ferme: "onglet Vinted fermé",
};

function texte(id: string, valeur: string): void {
  const el = document.getElementById(id);
  if (el) el.textContent = valeur;
}

function afficher(etat: Etat): void {
  const statut = document.getElementById("statut")!;
  statut.textContent = LIBELLES[etat.statut];
  statut.className = `statut ${etat.statut}`;
  texte("vinted", etat.vinted_login ? `${etat.vinted_login} (${etat.vinted_user_id})` : "—");
  texte("compte", etat.compte_nom ?? "—");
  texte("brouillons", `${etat.brouillons_du_jour}/${etat.brouillons_max_jour}`);
  texte(
    "action",
    etat.derniere_action
      ? `${new Date(etat.derniere_action.date).toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit" })} · ${etat.derniere_action.texte}`
      : "—",
  );
  const message = document.getElementById("message")!;
  message.hidden = !etat.message;
  message.textContent = etat.message ?? "";
  const bouton = document.getElementById("bascule") as HTMLButtonElement;
  bouton.textContent = etat.statut === "pause" ? "Reprendre" : "Pause";
  bouton.disabled = etat.statut === "non_configure";
}

async function charger(): Promise<Etat> {
  const { etat } = (await chrome.storage.local.get("etat")) as { etat?: Etat };
  return { ...ETAT_INITIAL, ...etat };
}

document.getElementById("bascule")!.addEventListener("click", async () => {
  const etat = await charger();
  await chrome.runtime.sendMessage({ type: etat.statut === "pause" ? "reprendre" : "pause" });
});
document.getElementById("options")!.addEventListener("click", () => void chrome.runtime.openOptionsPage());
chrome.storage.onChanged.addListener((changes) => {
  if (changes.etat) afficher({ ...ETAT_INITIAL, ...(changes.etat.newValue as Etat) });
});
void charger().then(afficher);
void chrome.runtime.sendMessage({ type: "tick" });
