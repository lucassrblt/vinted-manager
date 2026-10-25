"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, History, Loader2, Mail, Pencil, PlugZap, Plus, Trash2, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { LignesSquelette } from "@/components/commun";
import { BoutonSynchro } from "@/components/mails/bouton-synchro";
import { Champ } from "@/components/stock/dialog-article";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { formatDateHeure } from "@/lib/format";
import type { CompteVinted, ConfigMails, SyncLog } from "@/lib/types";
import { cn } from "@/lib/utils";

const NOMS_PRESETS: Record<string, string> = { gmail: "Gmail", outlook: "Outlook / Hotmail", orange: "Orange" };

export function ConfigurationImap() {
  const qc = useQueryClient();
  const config = useQuery({ queryKey: ["imap", "config"], queryFn: () => api<ConfigMails>("/parametres/mails") });
  const journal = useQuery({ queryKey: ["imap", "logs"], queryFn: () => api<SyncLog[]>("/imap/logs") });
  const [edition, setEdition] = useState<CompteVinted | "nouveau" | null>(null);
  const [aSupprimer, setASupprimer] = useState<CompteVinted | null>(null);
  const [expediteurs, setExpediteurs] = useState("");

  useEffect(() => {
    if (config.data) setExpediteurs(config.data.expediteurs.join(", "));
  }, [config.data]);

  const rafraichir = () => {
    qc.invalidateQueries({ queryKey: ["imap"] });
    qc.invalidateQueries({ queryKey: ["comptes"] });
  };
  const basculer = useMutation({
    mutationFn: (c: CompteVinted) =>
      api(`/comptes/${c.id}`, {
        method: "PUT",
        body: {
          nom: c.nom,
          serveur: c.imap_serveur,
          port: c.imap_port,
          email: c.imap_email,
          dossier: c.imap_dossier,
          actif: !c.actif,
        },
      }),
    onSuccess: rafraichir,
    onError: (e: Error) => toast.error(e.message),
  });
  const relire = useMutation({
    mutationFn: (c: CompteVinted) => api(`/comptes/${c.id}/relire`, { method: "POST" }),
    onSuccess: () => {
      rafraichir();
      toast.success("Toute la boîte sera relue à la prochaine synchro");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const supprimer = useMutation({
    mutationFn: (c: CompteVinted) => api(`/comptes/${c.id}`, { method: "DELETE" }),
    onSuccess: () => {
      rafraichir();
      toast.success("Boîte débranchée");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const enregistrerExpediteurs = useMutation({
    mutationFn: () =>
      api("/parametres/mails/expediteurs", {
        method: "PUT",
        body: {
          expediteurs: expediteurs
            .split(",")
            .map((x) => x.trim())
            .filter(Boolean),
        },
      }),
    onSuccess: () => {
      rafraichir();
      toast.success("Expéditeurs enregistrés");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (!config.data) return <LignesSquelette n={6} />;
  const comptes = config.data.comptes;
  const noms = Object.fromEntries(comptes.map((c) => [c.id, c.nom]));

  return (
    <div className="grid max-w-5xl gap-5 lg:grid-cols-[1fr_340px]">
      <div className="space-y-5">
        <section className="space-y-4 rounded-xl border bg-card p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">Comptes Vinted</h2>
              <p className="text-xs text-muted-foreground">
                Une boîte mail par compte : ventes, messages, offres et bordereaux sont lus toutes les 5 minutes.
              </p>
            </div>
            <Button size="sm" onClick={() => setEdition("nouveau")}>
              <Plus /> Ajouter une boîte
            </Button>
          </div>

          {comptes.length === 0 ? (
            <button
              type="button"
              onClick={() => setEdition("nouveau")}
              className="flex w-full flex-col items-center gap-2 rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground outline-none hover:bg-muted/50 focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              <Mail className="size-5" />
              Branche la boîte mail de ton premier compte Vinted
            </button>
          ) : (
            <ul className="divide-y rounded-lg border">
              {comptes.map((c) => (
                <li key={c.id} className="flex flex-wrap items-center gap-3 p-3">
                  <div className="min-w-0 flex-1">
                    <p className={cn("font-medium", !c.actif && "text-muted-foreground")}>
                      {c.nom}
                      {!c.actif && <span className="ml-2 text-xs font-normal">· en pause</span>}
                    </p>
                    <p className="truncate text-sm text-muted-foreground">
                      {c.imap_email ?? "Aucune boîte mail : clique sur le crayon pour en brancher une"}
                    </p>
                    <p className="text-xs text-muted-foreground tabular-nums">
                      {c.derniere_synchro ? `Synchro : ${formatDateHeure(c.derniere_synchro)}` : "Jamais synchronisée"}
                      {" · "}
                      {c.nb_mails} mail(s) · {c.nb_articles} article(s)
                    </p>
                  </div>
                  <Switch
                    checked={c.actif}
                    disabled={!c.imap_email}
                    onCheckedChange={() => basculer.mutate(c)}
                    aria-label={c.actif ? `Mettre ${c.nom} en pause` : `Réactiver ${c.nom}`}
                  />
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    onClick={() => relire.mutate(c)}
                    disabled={relire.isPending}
                    aria-label={`Relire tout l'historique de ${c.nom}`}
                    title="Relire tout l'historique de la boîte"
                  >
                    <History />
                  </Button>
                  <Button size="icon-sm" variant="ghost" onClick={() => setEdition(c)} aria-label={`Modifier ${c.nom}`}>
                    <Pencil />
                  </Button>
                  <Button
                    size="icon-sm"
                    variant="ghost"
                    onClick={() => setASupprimer(c)}
                    aria-label={`Débrancher ${c.nom}`}
                  >
                    <Trash2 />
                  </Button>
                </li>
              ))}
            </ul>
          )}
          <p className="text-xs text-muted-foreground">
            Les mots de passe sont chiffrés sur le serveur. Les mails sont lus en lecture seule : jamais supprimés,
            déplacés ni marqués comme lus.
          </p>
        </section>

        <form
          className="flex flex-wrap items-end gap-3 rounded-xl border bg-card p-5"
          onSubmit={(e) => {
            e.preventDefault();
            enregistrerExpediteurs.mutate();
          }}
        >
          <Champ id="imap-exp" libelle="Expéditeurs lus (séparés par des virgules)" className="min-w-60 flex-1">
            <Input id="imap-exp" value={expediteurs} onChange={(e) => setExpediteurs(e.target.value)} />
          </Champ>
          <Button type="submit" variant="outline" disabled={enregistrerExpediteurs.isPending}>
            Enregistrer
          </Button>
        </form>
      </div>

      <section className="space-y-3 rounded-xl border bg-card p-5">
        <h2 className="text-sm font-semibold">Journal de synchronisation</h2>
        <BoutonSynchro />
        {journal.data?.length ? (
          <ul className="space-y-2 text-sm">
            {journal.data.slice(0, 12).map((l) => (
              <li key={l.id} className="border-t pt-2">
                <div className="flex items-center justify-between gap-2">
                  <span className="tabular-nums">
                    {formatDateHeure(l.debut)}
                    {l.compte_id && noms[l.compte_id] && (
                      <span className="ml-1.5 text-xs text-muted-foreground">· {noms[l.compte_id]}</span>
                    )}
                  </span>
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

      <DialogCompte
        compte={edition}
        presets={config.data.presets}
        numero={comptes.length + 1}
        onFermer={() => setEdition(null)}
        onEnregistre={rafraichir}
      />

      <AlertDialog open={!!aSupprimer} onOpenChange={(o) => !o && setASupprimer(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Débrancher {aSupprimer?.nom} ?</AlertDialogTitle>
            <AlertDialogDescription>
              La boîte {aSupprimer?.imap_email} ne sera plus lue. Les mails, ventes et articles déjà importés sont
              conservés.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={() => aSupprimer && supprimer.mutate(aSupprimer)}>
              Débrancher
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}

function DialogCompte({
  compte,
  presets,
  numero,
  onFermer,
  onEnregistre,
}: {
  compte: CompteVinted | "nouveau" | null;
  presets: ConfigMails["presets"];
  numero: number;
  onFermer: () => void;
  onEnregistre: () => void;
}) {
  const existant = compte && compte !== "nouveau" ? compte : null;
  const [f, setF] = useState({ nom: "", serveur: "", port: "993", email: "", mot_de_passe: "", dossier: "INBOX" });
  const [resultatTest, setResultatTest] = useState<{ ok: boolean; message: string } | null>(null);

  useEffect(() => {
    if (!compte) return;
    setResultatTest(null);
    setF(
      existant
        ? {
            nom: existant.nom,
            serveur: existant.imap_serveur ?? "imap.gmail.com",
            port: String(existant.imap_port),
            email: existant.imap_email ?? "",
            mot_de_passe: "",
            dossier: existant.imap_dossier,
          }
        : {
            nom: `Compte ${numero}`,
            serveur: "imap.gmail.com",
            port: "993",
            email: "",
            mot_de_passe: "",
            dossier: "INBOX",
          },
    );
  }, [compte, existant, numero]);

  const corps = () => ({
    nom: f.nom.trim(),
    serveur: f.serveur,
    port: Number(f.port) || 993,
    email: f.email,
    mot_de_passe: f.mot_de_passe || null,
    dossier: f.dossier || "INBOX",
    actif: existant?.actif ?? true,
  });
  const tester = useMutation({
    mutationFn: () =>
      api<{ ok: boolean; message: string }>("/imap/test", { body: { ...corps(), compte_id: existant?.id ?? null } }),
    onSuccess: setResultatTest,
    onError: (e: Error) => setResultatTest({ ok: false, message: e.message }),
  });
  const enregistrer = useMutation({
    mutationFn: () =>
      existant ? api(`/comptes/${existant.id}`, { method: "PUT", body: corps() }) : api("/comptes", { body: corps() }),
    onSuccess: () => {
      onEnregistre();
      onFermer();
      toast.success(existant ? "Boîte modifiée" : "Boîte branchée : les mails arrivent à la prochaine synchro");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const incomplet = !f.nom.trim() || !f.serveur || !f.email || (!existant && !f.mot_de_passe);

  return (
    <Dialog open={!!compte} onOpenChange={(o) => !o && onFermer()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{existant ? `Modifier ${existant.nom}` : "Brancher une boîte mail"}</DialogTitle>
          <DialogDescription>L&apos;adresse qui reçoit les mails de ce compte Vinted.</DialogDescription>
        </DialogHeader>
        <form
          className="space-y-4"
          onSubmit={(e) => {
            e.preventDefault();
            enregistrer.mutate();
          }}
        >
          <Champ id="compte-nom" libelle="Nom du compte (pour t'y retrouver)">
            <Input
              id="compte-nom"
              value={f.nom}
              onChange={(e) => setF({ ...f, nom: e.target.value })}
              placeholder="Compte perso"
              maxLength={80}
            />
          </Champ>
          <div className="flex flex-wrap gap-2">
            {Object.entries(presets).map(([cle, p]) => (
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
          <div className="grid gap-4 sm:grid-cols-[1fr_90px]">
            <Champ id="imap-serveur" libelle="Serveur IMAP">
              <Input id="imap-serveur" value={f.serveur} onChange={(e) => setF({ ...f, serveur: e.target.value })} />
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
              placeholder={existant ? "Enregistré (laisser vide pour le garder)" : ""}
            />
          </Champ>
          {f.serveur.includes("gmail") && (
            <p className="rounded-lg bg-muted/60 p-3 text-xs leading-relaxed text-muted-foreground">
              Gmail refuse ton mot de passe habituel. Active la validation en deux étapes sur ce compte Google, puis
              crée un mot de passe d&apos;application sur{" "}
              <a
                className="underline"
                href="https://myaccount.google.com/apppasswords"
                target="_blank"
                rel="noreferrer"
              >
                myaccount.google.com/apppasswords
              </a>{" "}
              et colle les 16 caractères ici.
            </p>
          )}
          <Champ id="imap-dossier" libelle="Dossier surveillé">
            <Input id="imap-dossier" value={f.dossier} onChange={(e) => setF({ ...f, dossier: e.target.value })} />
          </Champ>

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
      </DialogContent>
    </Dialog>
  );
}
