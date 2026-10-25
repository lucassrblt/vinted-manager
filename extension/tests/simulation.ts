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
  notifications: Gestion = () => ({ ok: true, resultat: { source: "api", notifications: [] } });
  verifier_compte: Gestion = () => ({ ok: true, resultat: { id: 3201823662, login: "jeanmekloul" } });
  relance: Gestion = () => ({ ok: true, resultat: { conversation_id: "c", transaction_id: "1", offre_envoyee: true } });
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
  let memoire: Memoire = {
    ...MEMOIRE_INITIALE,
    dernierDressing: horloge,
    derniereInbox: horloge,
    dernieresNotifications: horloge,
    ...o.memoire,
  };
  const attentes: number[] = [];
  const navigations: string[] = [];
  // URL finale de la page « want_it » (null : pas de redirection dans le délai).
  let redirection: string | null = "https://www.vinted.fr/inbox/01a1729a-df35-7e50-84fc-f46b8ec2dc6a";
  const sim = {
    backend,
    contenu,
    attentes,
    navigations,
    memoire: () => memoire,
    rediriger(url: string | null) {
      redirection = url;
    },
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
    ongletTravail: {
      naviguer: async (url, attendue) => {
        navigations.push(url);
        if (!url.includes("want_it")) return url;
        return redirection !== null && attendue(redirection) ? redirection : null;
      },
    },
  };
  sim.moteur = new Moteur(env);
  return sim;
}
