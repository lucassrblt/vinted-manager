/** Environnement simulé du service worker : faux backend, faux onglet, horloge contrôlée. */
import { ETAT_INITIAL, type Etat } from "../src/etat";
import { type Environnement, MEMOIRE_INITIALE, type Memoire, Moteur } from "../src/moteur";
import type { Reponse, VersContenu } from "../src/protocole";
import { FauxBackend } from "./fauxBackend";

type Gestion = (payload: never) => Reponse;

export class ContenuSimule {
  compte: Gestion = () => ({ ok: true, resultat: { id: 3201823662, login: "jeanmekloul" } });
  brouillon: Gestion = () => ({ ok: false, erreur: "non prévu", arret: false, mauvais_compte: false });
  messages: VersContenu[] = [];

  repondre(m: VersContenu): Reponse {
    this.messages.push(m);
    const g = (this as unknown as Record<string, Gestion | undefined>)[m.type];
    if (!g) return { ok: false, erreur: `message ${m.type} non simulé`, arret: false, mauvais_compte: false };
    return g(m.payload as never);
  }
}

export function environnement(o: { configure?: boolean; onglet?: number | null; aleatoire?: number } = {}) {
  const backend = new FauxBackend();
  const contenu = new ContenuSimule();
  let horloge = Date.UTC(2026, 9, 25, 12, 0, 0);
  let memoire: Memoire = { ...MEMOIRE_INITIALE };
  const sim = {
    backend,
    contenu,
    etat: { ...ETAT_INITIAL } as Etat,
    avancer(ms: number) {
      horloge += ms;
    },
    moteur: null as unknown as Moteur,
  };
  const env: Environnement = {
    backend: o.configure === false ? null : backend.client(),
    ongletVinted: async () => (o.onglet === undefined ? 7 : o.onglet),
    envoyer: async <R>(_onglet: number, m: VersContenu) => contenu.repondre(m) as Reponse<R>,
    maintenant: () => horloge,
    aleatoire: () => o.aleatoire ?? 0.5,
    lireMemoire: async () => ({ ...memoire }),
    ecrireMemoire: async (m) => {
      memoire = { ...m };
    },
    majEtat: async (p) => {
      sim.etat = { ...sim.etat, ...p };
    },
    version: "0.1.0",
  };
  sim.moteur = new Moteur(env);
  return sim;
}
