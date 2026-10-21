"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, Info, Loader2, Smartphone, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { LignesSquelette } from "@/components/commun";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { formatDateHeure } from "@/lib/format";
import {
  abonnementActuel,
  activerSurCetAppareil,
  desactiverSurCetAppareil,
  estInstallee,
  estIos,
  pushSupporte,
} from "@/lib/push";

interface Appareil {
  id: number;
  endpoint: string;
  user_agent: string | null;
  created_at: string;
}
type Preferences = Record<"vente" | "litige" | "offre" | "rappel_envois", boolean>;

const TYPES: { cle: keyof Preferences; libelle: string; aide: string }[] = [
  { cle: "vente", libelle: "Nouvelle vente détectée", aide: "Dès qu'un mail de vente Vinted arrive." },
  { cle: "litige", libelle: "Nouveau litige", aide: "Un acheteur a signalé un problème." },
  { cle: "offre", libelle: "Nouvelle offre", aide: "Une offre a été reçue sur un article." },
  { cle: "rappel_envois", libelle: "Rappel de 9 h", aide: "Les colis à déposer dans la journée et ceux en retard." },
];

function nomAppareil(ua: string | null): string {
  if (!ua) return "Appareil inconnu";
  const systeme = /iPhone/.test(ua)
    ? "iPhone"
    : /iPad/.test(ua)
      ? "iPad"
      : /Android/.test(ua)
        ? "Android"
        : /Mac/.test(ua)
          ? "Mac"
          : /Windows/.test(ua)
            ? "Windows"
            : "Ordinateur";
  const navigateur = /Edg\//.test(ua)
    ? "Edge"
    : /Chrome\//.test(ua)
      ? "Chrome"
      : /Firefox\//.test(ua)
        ? "Firefox"
        : /Safari\//.test(ua)
          ? "Safari"
          : "navigateur";
  return `${systeme} · ${navigateur}`;
}

export function ParametresNotifications() {
  const qc = useQueryClient();
  const config = useQuery({
    queryKey: ["push", "config"],
    queryFn: () => api<{ cle_publique: string | null; configure: boolean }>("/push/config"),
  });
  const appareils = useQuery({ queryKey: ["push", "appareils"], queryFn: () => api<Appareil[]>("/push/abonnements") });
  const prefs = useQuery({ queryKey: ["push", "prefs"], queryFn: () => api<Preferences>("/parametres/notifications") });
  const [endpointLocal, setEndpointLocal] = useState<string | null>(null);
  const [env, setEnv] = useState({ supporte: true, ios: false, installee: false });

  useEffect(() => {
    setEnv({ supporte: pushSupporte(), ios: estIos(), installee: estInstallee() });
    abonnementActuel().then((a) => setEndpointLocal(a?.endpoint ?? null));
  }, []);

  const invalider = () => qc.invalidateQueries({ queryKey: ["push"] });
  const activer = useMutation({
    mutationFn: () => activerSurCetAppareil(config.data!.cle_publique!),
    onSuccess: async () => {
      setEndpointLocal((await abonnementActuel())?.endpoint ?? null);
      invalider();
      toast.success("Notifications activées sur cet appareil");
    },
    onError: (e: Error) => toast.error(e.message, { duration: 8000 }),
  });
  const supprimer = useMutation({
    mutationFn: async (a: Appareil) => {
      if (a.endpoint === endpointLocal) await desactiverSurCetAppareil();
      await api(`/push/abonnements/${a.id}`, { method: "DELETE" });
    },
    onSuccess: async () => {
      setEndpointLocal((await abonnementActuel())?.endpoint ?? null);
      invalider();
      toast.success("Appareil retiré");
    },
  });
  const tester = useMutation({
    mutationFn: () => api<{ appareils: number }>("/push/test", { method: "POST" }),
    onSuccess: (r) => toast.success(`Notification envoyée à ${r.appareils} appareil(s)`),
    onError: (e: Error) => toast.error(e.message),
  });
  const majPrefs = useMutation({
    mutationFn: (p: Preferences) => api<Preferences>("/parametres/notifications", { method: "PUT", body: p }),
    onSuccess: (p) => qc.setQueryData(["push", "prefs"], p),
    onError: (e: Error) => toast.error(e.message),
  });

  if (!config.data || !prefs.data) return <LignesSquelette n={5} />;
  const actifIci = !!endpointLocal && (appareils.data ?? []).some((a) => a.endpoint === endpointLocal);

  return (
    <div className="grid max-w-5xl gap-5 lg:grid-cols-[1fr_360px]">
      <div className="space-y-5">
        {env.ios && !env.installee && (
          <div className="flex gap-3 rounded-xl border border-sky-200 bg-sky-50 p-4 text-sm dark:border-sky-900 dark:bg-sky-950/40">
            <Info className="mt-0.5 size-4 shrink-0 text-sky-700 dark:text-sky-300" />
            <div className="space-y-1">
              <p className="font-medium">
                Sur iPhone, installe d&apos;abord l&apos;app sur l&apos;écran d&apos;accueil
              </p>
              <p className="text-muted-foreground">
                Apple n&apos;autorise les notifications que pour les apps installées : dans Safari, touche le bouton
                Partager puis « Sur l&apos;écran d&apos;accueil ». Ouvre ensuite Revente depuis son icône et reviens ici
                pour activer les notifications.
              </p>
            </div>
          </div>
        )}
        {!config.data.configure && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
            Les notifications ne sont pas configurées sur le serveur : ajoute VAPID_PUBLIC_KEY et VAPID_PRIVATE_KEY
            (voir le README, commande <code>python -m app.cli vapid-keys</code>).
          </p>
        )}

        <section className="rounded-xl border bg-card p-5">
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-brand-soft text-brand">
              <BellRing className="size-5" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="font-medium">Cet appareil</p>
              <p className="text-sm text-muted-foreground">
                {!env.supporte
                  ? "Ce navigateur ne gère pas les notifications push."
                  : actifIci
                    ? "Les notifications sont activées."
                    : "Les notifications ne sont pas activées."}
              </p>
            </div>
            {actifIci ? (
              <Button variant="outline" onClick={() => tester.mutate()} disabled={tester.isPending}>
                {tester.isPending && <Loader2 className="animate-spin" />}
                Envoyer une notification de test
              </Button>
            ) : (
              <Button
                onClick={() => activer.mutate()}
                disabled={!env.supporte || !config.data.configure || activer.isPending || (env.ios && !env.installee)}
              >
                {activer.isPending && <Loader2 className="animate-spin" />}
                Activer les notifications sur cet appareil
              </Button>
            )}
          </div>
        </section>

        <section className="rounded-xl border bg-card p-5">
          <h2 className="mb-3 text-sm font-semibold">Quelles notifications ?</h2>
          <ul className="divide-y">
            {TYPES.map((t) => (
              <li key={t.cle} className="flex items-center gap-3 py-3">
                <div className="min-w-0 flex-1">
                  <p className="text-sm font-medium">{t.libelle}</p>
                  <p className="text-xs text-muted-foreground">{t.aide}</p>
                </div>
                <Switch
                  aria-label={t.libelle}
                  checked={prefs.data[t.cle]}
                  onCheckedChange={(v) => majPrefs.mutate({ ...prefs.data!, [t.cle]: v })}
                />
              </li>
            ))}
          </ul>
        </section>
      </div>

      <section className="space-y-3 rounded-xl border bg-card p-5">
        <h2 className="text-sm font-semibold">Appareils abonnés</h2>
        {appareils.data?.length ? (
          <ul className="space-y-2">
            {appareils.data.map((a) => (
              <li key={a.id} className="flex items-center gap-2 rounded-lg border px-3 py-2 text-sm">
                <Smartphone className="size-4 text-muted-foreground" />
                <span className="min-w-0 flex-1">
                  <span className="block truncate">
                    {nomAppareil(a.user_agent)}
                    {a.endpoint === endpointLocal && <span className="text-brand"> · cet appareil</span>}
                  </span>
                  <span className="text-xs text-muted-foreground">depuis le {formatDateHeure(a.created_at)}</span>
                </span>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Retirer l'appareil"
                  onClick={() => supprimer.mutate(a)}
                >
                  <Trash2 />
                </Button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">Aucun appareil pour l&apos;instant.</p>
        )}
      </section>
    </div>
  );
}
