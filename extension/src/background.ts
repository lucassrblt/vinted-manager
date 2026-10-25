/** Service worker : alarmes, file d'actions, échanges avec le backend et l'onglet Vinted. */
import { ClientBackend } from "./backend";
import { BACKEND_DEFAUT, type Config, ETAT_INITIAL, type Etat } from "./etat";
import { MEMOIRE_INITIALE, type Memoire, Moteur, reponseIndisponible } from "./moteur";
import { attendre, blobVersBase64 } from "./outils";
import type { PhotoBase64, Reponse, VersContenu, VersFond } from "./protocole";

const ALARME = "tick";

async function config(): Promise<Config | null> {
  const { config } = (await chrome.storage.local.get("config")) as { config?: Config };
  if (!config?.jeton) return null;
  return { backendUrl: config.backendUrl || BACKEND_DEFAUT, jeton: config.jeton };
}

async function backend(): Promise<ClientBackend | null> {
  const c = await config();
  return c ? new ClientBackend((url, init) => fetch(url, init), c.backendUrl, c.jeton) : null;
}

async function majEtat(partiel: Partial<Etat>): Promise<void> {
  const { etat } = (await chrome.storage.local.get("etat")) as { etat?: Etat };
  await chrome.storage.local.set({ etat: { ...ETAT_INITIAL, ...etat, ...partiel } });
}

/** Un onglet www.vinted.fr ouvert par Lucas (l'onglet de travail de l'extension est exclu). */
async function ongletVinted(): Promise<number | null> {
  const { ongletTravail } = (await chrome.storage.session.get("ongletTravail")) as { ongletTravail?: number };
  const onglets = await chrome.tabs.query({ url: "https://www.vinted.fr/*" });
  const onglet = onglets.find((o) => o.id !== undefined && o.id !== ongletTravail && o.status === "complete");
  return onglet?.id ?? null;
}

async function envoyer<R>(onglet: number, message: VersContenu): Promise<Reponse<R>> {
  try {
    const r = (await chrome.tabs.sendMessage(onglet, message)) as Reponse<R> | undefined;
    return r ?? reponseIndisponible("L'onglet Vinted n'a pas répondu.");
  } catch {
    return reponseIndisponible("L'onglet Vinted ne répond pas (page en cours de chargement ?).");
  }
}

/** Onglet de travail : ouvert en arrière-plan par l'extension et réutilisé (jamais l'onglet de Lucas).
 * Renvoie son identifiant et l'URL qu'il affichait avant la navigation. */
async function ongletDeTravail(url: string): Promise<{ id: number; avant: string }> {
  const { ongletTravail } = (await chrome.storage.session.get("ongletTravail")) as { ongletTravail?: number };
  if (ongletTravail !== undefined) {
    try {
      const avant = (await chrome.tabs.get(ongletTravail)).url ?? "";
      await chrome.tabs.update(ongletTravail, { url });
      return { id: ongletTravail, avant };
    } catch {
      /* onglet fermé : on en ouvre un autre */
    }
  }
  const onglet = await chrome.tabs.create({ url, active: false });
  await chrome.storage.session.set({ ongletTravail: onglet.id });
  return { id: onglet.id as number, avant: "" };
}

async function naviguer(url: string, attendue: (url: string) => boolean, delaiMs: number): Promise<string | null> {
  const { id, avant } = await ongletDeTravail(url);
  const fin = Date.now() + delaiMs;
  while (Date.now() < fin) {
    await attendre(500);
    try {
      const onglet = await chrome.tabs.get(id);
      // L'URL en cours de chargement d'abord : `url` reste l'ancienne page tant que la nouvelle n'est pas validée.
      const actuelle = onglet.pendingUrl ?? onglet.url ?? "";
      if (actuelle && actuelle !== url && actuelle !== avant && attendue(actuelle)) return actuelle;
    } catch {
      return null;
    }
  }
  return null;
}

/** Images publiques de Vinted (CDN), sans cookie : elles n'agissent pas sur le compte. */
async function telecharger(url: string): Promise<Blob> {
  if (!/^https:\/\/[a-z0-9-]+\.vinted\.net\//.test(url)) throw new Error(`Adresse d'image refusée : ${url}`);
  const res = await fetch(url, { credentials: "omit" });
  if (!res.ok) throw new Error(`Image indisponible (${res.status}).`);
  return res.blob();
}

let enCours: Promise<void> | null = null;

async function moteur(): Promise<Moteur> {
  return new Moteur({
    backend: await backend(),
    ongletVinted,
    envoyer,
    maintenant: () => Date.now(),
    attendre,
    aleatoire: Math.random,
    lireMemoire: async () =>
      ((await chrome.storage.local.get("memoire")) as { memoire?: Memoire }).memoire ?? { ...MEMOIRE_INITIALE },
    ecrireMemoire: (memoire) => chrome.storage.local.set({ memoire }),
    majEtat,
    ongletTravail: { naviguer },
    telecharger,
    version: chrome.runtime.getManifest().version,
  });
}

async function tick(): Promise<void> {
  if (enCours) return; // un seul cycle à la fois
  enCours = (async () => {
    await (await moteur()).tick();
  })();
  try {
    await enCours;
  } finally {
    enCours = null;
  }
}

function demarrer(): void {
  void chrome.alarms.create(ALARME, { periodInMinutes: 0.5 }); // minimum autorisé en MV3
  void tick();
}

chrome.runtime.onInstalled.addListener(demarrer);
chrome.runtime.onStartup.addListener(demarrer);
chrome.alarms.onAlarm.addListener((alarme) => {
  if (alarme.name === ALARME) void tick();
});

chrome.runtime.onMessage.addListener(
  (message: VersFond | { type: "tick" | "pause" | "reprendre" }, _expediteur, repondre) => {
    void (async () => {
      if (message.type === "photo") {
        const b = await backend();
        if (!b)
          return repondre({ ok: false, erreur: "Extension non configurée.", arret: false, mauvais_compte: false });
        try {
          const ref = message.payload;
          const octets = "photo_id" in ref ? await b.photo(ref.photo_id) : await b.photoTache(ref.tache_id, ref.index);
          repondre({ ok: true, resultat: { base64: blobVersBase64(octets) } } satisfies Reponse<PhotoBase64>);
        } catch (e) {
          repondre({ ok: false, erreur: (e as Error).message, arret: false, mauvais_compte: false });
        }
        return;
      }
      if (message.type === "pause" || message.type === "reprendre") {
        const b = await backend();
        if (b) {
          const compte = await b.pause(message.type === "pause");
          await majEtat({ statut: compte.pause ? "pause" : "actif", message: compte.pause_raison });
        }
        repondre({ ok: true });
        return;
      }
      if (message.type === "tick") {
        await tick();
        repondre({ ok: true });
      }
    })();
    return true; // réponse asynchrone
  },
);
