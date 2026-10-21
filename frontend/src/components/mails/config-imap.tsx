"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Loader2, PlugZap, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { LignesSquelette } from "@/components/commun";
import { BoutonSynchro } from "@/components/mails/bouton-synchro";
import { Champ } from "@/components/stock/dialog-article";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { formatDateHeure } from "@/lib/format";
import type { ConfigImap, SyncLog } from "@/lib/types";
import { cn } from "@/lib/utils";

const NOMS_PRESETS: Record<string, string> = { gmail: "Gmail", outlook: "Outlook / Hotmail", orange: "Orange" };

export function ConfigurationImap() {
  const qc = useQueryClient();
  const config = useQuery({ queryKey: ["imap", "config"], queryFn: () => api<ConfigImap>("/parametres/imap") });
  const journal = useQuery({ queryKey: ["imap", "logs"], queryFn: () => api<SyncLog[]>("/imap/logs") });
  const [f, setF] = useState({
    serveur: "",
    port: "993",
    email: "",
    mot_de_passe: "",
    dossier: "INBOX",
    expediteurs: "vinted",
  });
  const [resultatTest, setResultatTest] = useState<{ ok: boolean; message: string } | null>(null);

  useEffect(() => {
    const c = config.data;
    if (c)
      setF({
        serveur: c.serveur ?? "",
        port: String(c.port ?? 993),
        email: c.email ?? "",
        mot_de_passe: "",
        dossier: c.dossier,
        expediteurs: c.expediteurs.join(", "),
      });
  }, [config.data]);

  const corps = () => ({
    serveur: f.serveur,
    port: Number(f.port) || 993,
    email: f.email,
    mot_de_passe: f.mot_de_passe || null,
    dossier: f.dossier || "INBOX",
    expediteurs: f.expediteurs
      .split(",")
      .map((x) => x.trim())
      .filter(Boolean),
  });

  const tester = useMutation({
    mutationFn: () => api<{ ok: boolean; message: string }>("/imap/test", { body: corps() }),
    onSuccess: setResultatTest,
    onError: (e: Error) => setResultatTest({ ok: false, message: e.message }),
  });
  const enregistrer = useMutation({
    mutationFn: () => api<ConfigImap>("/parametres/imap", { method: "PUT", body: corps() }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["imap"] });
      toast.success("Boîte mail enregistrée : synchronisation toutes les 5 minutes");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (!config.data) return <LignesSquelette n={6} />;
  const motDePasseRequis = !config.data.mot_de_passe_defini && !f.mot_de_passe;
  const incomplet = !f.serveur || !f.email || motDePasseRequis;

  return (
    <div className="grid max-w-5xl gap-5 lg:grid-cols-[1fr_340px]">
      <form
        className="space-y-5 rounded-xl border bg-card p-5"
        onSubmit={(e) => {
          e.preventDefault();
          enregistrer.mutate();
        }}
      >
        <div>
          <p className="mb-2 text-sm font-medium">Fournisseur</p>
          <div className="flex flex-wrap gap-2">
            {Object.entries(config.data.presets).map(([cle, p]) => (
              <Button
                key={cle}
                type="button"
                variant="outline"
                size="sm"
                className={cn(f.serveur === p.serveur && "border-brand bg-brand-soft/50")}
                onClick={() => setF({ ...f, serveur: p.serveur, port: String(p.port) })}
              >
                {NOMS_PRESETS[cle] ?? cle}
              </Button>
            ))}
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-[1fr_100px]">
          <Champ id="imap-serveur" libelle="Serveur IMAP">
            <Input
              id="imap-serveur"
              value={f.serveur}
              onChange={(e) => setF({ ...f, serveur: e.target.value })}
              placeholder="imap.gmail.com"
            />
          </Champ>
          <Champ id="imap-port" libelle="Port">
            <Input
              id="imap-port"
              inputMode="numeric"
              value={f.port}
              onChange={(e) => setF({ ...f, port: e.target.value.replace(/\D/g, "") })}
            />
          </Champ>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Champ id="imap-email" libelle="Adresse email">
            <Input
              id="imap-email"
              type="email"
              autoComplete="off"
              value={f.email}
              onChange={(e) => setF({ ...f, email: e.target.value })}
            />
          </Champ>
          <Champ id="imap-mdp" libelle="Mot de passe d'application">
            <Input
              id="imap-mdp"
              type="password"
              autoComplete="new-password"
              value={f.mot_de_passe}
              onChange={(e) => setF({ ...f, mot_de_passe: e.target.value })}
              placeholder={config.data.mot_de_passe_defini ? "Enregistré (laisser vide pour le garder)" : ""}
            />
          </Champ>
        </div>
        {f.serveur.includes("gmail") && (
          <p className="rounded-lg bg-muted/60 p-3 text-xs leading-relaxed text-muted-foreground">
            Gmail refuse ton mot de passe habituel. Active la validation en deux étapes sur ton compte Google, puis crée
            un mot de passe d&apos;application sur{" "}
            <a className="underline" href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer">
              myaccount.google.com/apppasswords
            </a>{" "}
            et colle les 16 caractères ici.
          </p>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Champ id="imap-dossier" libelle="Dossier surveillé">
            <Input id="imap-dossier" value={f.dossier} onChange={(e) => setF({ ...f, dossier: e.target.value })} />
          </Champ>
          <Champ id="imap-exp" libelle="Expéditeurs (séparés par des virgules)">
            <Input id="imap-exp" value={f.expediteurs} onChange={(e) => setF({ ...f, expediteurs: e.target.value })} />
          </Champ>
        </div>
        <p className="text-xs text-muted-foreground">
          Le mot de passe est chiffré sur le serveur. Les mails sont lus en lecture seule : jamais supprimés, déplacés
          ni marqués comme lus.
        </p>

        {resultatTest && (
          <div
            role="status"
            className={cn(
              "flex items-start gap-2 rounded-lg p-3 text-sm",
              resultatTest.ok ? "bg-brand-soft text-brand" : "bg-destructive/10 text-destructive",
            )}
          >
            {resultatTest.ok ? (
              <CheckCircle2 className="mt-0.5 size-4 shrink-0" />
            ) : (
              <XCircle className="mt-0.5 size-4 shrink-0" />
            )}
            <span>{resultatTest.message}</span>
          </div>
        )}

        <div className="flex flex-wrap justify-end gap-2">
          <Button
            type="button"
            variant="outline"
            onClick={() => tester.mutate()}
            disabled={incomplet || tester.isPending}
          >
            {tester.isPending ? <Loader2 className="animate-spin" /> : <PlugZap />}
            Tester la connexion
          </Button>
          <Button type="submit" disabled={incomplet || enregistrer.isPending}>
            {enregistrer.isPending && <Loader2 className="animate-spin" />}
            Enregistrer
          </Button>
        </div>
      </form>

      <section className="space-y-3 rounded-xl border bg-card p-5">
        <h2 className="text-sm font-semibold">Journal de synchronisation</h2>
        <BoutonSynchro />
        {journal.data?.length ? (
          <ul className="space-y-2 text-sm">
            {journal.data.slice(0, 10).map((l) => (
              <li key={l.id} className="border-t pt-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="tabular-nums">{formatDateHeure(l.debut)}</span>
                  <span
                    className={cn("text-xs", l.erreur ? "text-red-600 dark:text-red-400" : "text-muted-foreground")}
                  >
                    {l.erreur ? "Erreur" : `${l.nb_mails} nouveau(x)`}
                  </span>
                </div>
                {l.erreur && <p className="mt-1 text-xs whitespace-pre-line text-muted-foreground">{l.erreur}</p>}
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-muted-foreground">Aucune synchronisation pour l&apos;instant.</p>
        )}
      </section>
    </div>
  );
}
