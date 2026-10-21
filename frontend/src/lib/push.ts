"use client";

import { api } from "@/lib/api";

export function pushSupporte(): boolean {
  return (
    typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window && "Notification" in window
  );
}

/** iPhone / iPad : les notifications ne marchent qu'une fois l'app installée sur l'écran d'accueil. */
export function estIos(): boolean {
  if (typeof navigator === "undefined") return false;
  return (
    /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1)
  );
}

export function estInstallee(): boolean {
  if (typeof window === "undefined") return false;
  return (
    window.matchMedia("(display-mode: standalone)").matches ||
    (navigator as Navigator & { standalone?: boolean }).standalone === true
  );
}

function cleVersUint8(base64: string): Uint8Array<ArrayBuffer> {
  const rembourre = (base64 + "=".repeat((4 - (base64.length % 4)) % 4)).replace(/-/g, "+").replace(/_/g, "/");
  const brut = atob(rembourre);
  const sortie = new Uint8Array(new ArrayBuffer(brut.length));
  for (let i = 0; i < brut.length; i++) sortie[i] = brut.charCodeAt(i);
  return sortie;
}

export async function abonnementActuel(): Promise<PushSubscription | null> {
  if (!pushSupporte()) return null;
  const reg = await navigator.serviceWorker.getRegistration();
  return (await reg?.pushManager.getSubscription()) ?? null;
}

export async function activerSurCetAppareil(clePublique: string): Promise<void> {
  if (!pushSupporte()) throw new Error("Ce navigateur ne gère pas les notifications push.");
  const permission = await Notification.requestPermission();
  if (permission !== "granted") {
    throw new Error("Notifications refusées : autorise-les dans les réglages du navigateur pour ce site.");
  }
  const reg = await navigator.serviceWorker.register("/sw.js");
  await navigator.serviceWorker.ready;
  const abonnement =
    (await reg.pushManager.getSubscription()) ??
    (await reg.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: cleVersUint8(clePublique) }));
  const json = abonnement.toJSON();
  await api("/push/abonnements", { body: { endpoint: json.endpoint, keys: json.keys } });
}

export async function desactiverSurCetAppareil(): Promise<void> {
  const abonnement = await abonnementActuel();
  await abonnement?.unsubscribe();
}
