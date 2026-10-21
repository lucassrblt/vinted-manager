// Service worker : notifications push et installation sur l'écran d'accueil.
// Pas de cache hors ligne : les données doivent toujours être fraîches.

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

// Gestionnaire réseau minimal (requis par certains navigateurs pour proposer l'installation).
self.addEventListener("fetch", () => {});

self.addEventListener("push", (event) => {
  let donnees = { titre: "Revente", corps: "", url: "/" };
  try {
    donnees = { ...donnees, ...event.data.json() };
  } catch {
    if (event.data) donnees.corps = event.data.text();
  }
  event.waitUntil(
    self.registration.showNotification(donnees.titre, {
      body: donnees.corps,
      icon: "/icons/icon-192.png",
      badge: "/icons/icon-192.png",
      data: { url: donnees.url },
      lang: "fr",
    }),
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = new URL(event.notification.data?.url || "/", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((fenetres) => {
      for (const fenetre of fenetres) {
        if (fenetre.url.startsWith(self.location.origin) && "focus" in fenetre) {
          fenetre.navigate(url);
          return fenetre.focus();
        }
      }
      return self.clients.openWindow(url);
    }),
  );
});
