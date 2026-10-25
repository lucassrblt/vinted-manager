/**
 * Pont dans le contexte de la page www.vinted.fr (« world: MAIN »).
 *
 * Le content script tourne dans un monde isolé : son `fetch` est celui du navigateur, sans ce que les
 * scripts de la page (dont la protection anti-robot) ajoutent aux requêtes du site, d'où des 403.
 * Ici, `window.fetch` est celui de la page, lu au moment de l'appel : les requêtes partent exactement
 * comme celles du site. Le content script dialogue avec ce pont par `window.postMessage`.
 */
import { executer, type RequetePont, SOURCE_CONTENU, SOURCE_PONT } from "./vinted/pont";

window.addEventListener("message", (e: MessageEvent) => {
  const d = e.data as { source?: string; id?: string; requete?: RequetePont } | null;
  if (e.source !== window || !d || d.source !== SOURCE_CONTENU || !d.id || !d.requete) return;
  void executer(d.requete, (url, init) => window.fetch(url, init)).then((reponse) =>
    window.postMessage({ source: SOURCE_PONT, id: d.id, reponse }, window.location.origin),
  );
});
