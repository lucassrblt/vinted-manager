/** Content script de www.vinted.fr : seul composant qui appelle Vinted (même origine, cookies du navigateur). */
import { Contenu } from "./contenu";
import { attendre } from "./outils";
import type { PhotoBase64, Reponse, VersContenu } from "./protocole";
import { nouvelId } from "./protocole";
import { ClientVinted, lireContexte } from "./vinted/client";
import { fetchParLaPage } from "./vinted/pont";

// Les appels passent par le pont installé dans la page (src/pont.ts) : mêmes requêtes que le site.
const fetchPage = fetchParLaPage(
  (message) => window.postMessage(message, window.location.origin),
  (rappel) => {
    const ecouteur = (e: MessageEvent) => {
      if (e.source === window) rappel(e.data);
    };
    window.addEventListener("message", ecouteur);
    return () => window.removeEventListener("message", ecouteur);
  },
);

const contenu = new Contenu({
  // Contexte relu à chaque action : le jeton CSRF peut changer pendant la session.
  client: () => new ClientVinted(fetchPage, lireContexte(document)),
  demanderPhoto: (ref) =>
    chrome.runtime.sendMessage({ type: "photo", id: nouvelId(), payload: ref }) as Promise<Reponse<PhotoBase64>>,
  attendre,
  maintenant: () => Date.now(),
  planifier: (fn, ms) => void setTimeout(fn, ms),
  signaler: (compteurs) => void chrome.runtime.sendMessage({ type: "compteurs", id: nouvelId(), payload: compteurs }),
  aleatoire: Math.random,
});

chrome.runtime.onMessage.addListener((message: VersContenu, _expediteur, repondre) => {
  void contenu.traiter(message).then(repondre);
  return true;
});
