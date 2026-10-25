/** Environnement simulé du service worker : faux backend, faux onglet, horloge contrôlée. */
import { ETAT_INITIAL, type Etat } from "../src/etat";
import { type Environnement, MEMOIRE_INITIALE, type Memoire, Moteur } from "../src/moteur";
import type { Reponse, VersContenu } from "../src/protocole";
import { FauxBackend } from "./fauxBackend";

type Gestion = (payload: never) => Reponse;

export class ContenuSimule {
  compte: Gestion = () => ({ ok: true, resultat: { id: 3201823662, login: "jeanmekloul" } });
  executer: Gestion = () => ({ ok: false, erreur: "non prévu", arret: false, mauvais_compte: false });
  surveillance: Gestion = () => ({ ok: true, resultat: null });
  dressing: Gestion = () => ({ ok: true, resultat: { items: [], complet: true, total: 0 } });
  inbox: Gestion = () => ({ ok: true, resultat: { conversations: [] } });
  conversation: Gestion = (p: never) => ({ ok: true, resultat: { id: (p as { id: string }).id, messages: [] } });
  messages: VersContenu[] = [];

  repondre(m: VersContenu): Reponse {
    this.messages.push(m);
    const g = (this as unknown as Record<string, Gestion | undefined>)[m.type];
    if (!g) return { ok: false, erreur: `message ${m.type} non simulé`, arret: false, mauvais_compte: false };
    return g(m.payload as never);
  }
}

export function environnement(o: { configure?: boolean; onglet?: number | null; memoire?: Partial<Memoire> } = {}) {
  const backend = new FauxBackend();
  const contenu = new ContenuSimule();
  let horloge = Date.UTC(2026, 9, 25, 12, 0, 0);
  // Par défaut, dressing et messagerie viennent d'être lus : les tests ciblent le reste.
  let memoire: Memoire = { ...MEMOIRE_INITIALE, dernierDressing: horloge, derniereInbox: horloge, ...o.memoire };
  const attentes: number[] = [];
  const sim = {
    backend,
    contenu,
    attentes,
    memoire: () => memoire,
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
    attendre: async (ms) => {
      attentes.push(ms);
    },
    aleatoire: () => 0.5,
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
