"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Copy, KeyRound, Loader2, Pause, Play, Plus, ShieldAlert } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { LignesSquelette } from "@/components/commun";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { copier } from "@/lib/copier";
import { formatDateHeure } from "@/lib/format";
import type { CompteAutomatisation, EntreeJournal } from "@/lib/types";
import { cn } from "@/lib/utils";

// L'extension envoie un signal de vie chaque minute.
const EN_LIGNE_MS = 3 * 60_000;

export function ParametresAutomatisation() {
  const qc = useQueryClient();
  const comptes = useQuery({
    queryKey: ["automatisation", "comptes"],
    queryFn: () => api<CompteAutomatisation[]>("/automatisation/comptes"),
    refetchInterval: 30_000,
  });
  const journal = useQuery({
    queryKey: ["automatisation", "journal"],
    queryFn: () => api<EntreeJournal[]>("/automatisation/journal", { params: { limite: 60 } }),
    refetchInterval: 30_000,
  });
  const [nom, setNom] = useState("");
  const [jeton, setJeton] = useState<{ compte: string; valeur: string } | null>(null);
  const rafraichir = () => qc.invalidateQueries({ queryKey: ["automatisation"] });

  const creer = useMutation({
    mutationFn: () => api("/automatisation/comptes", { body: { nom: nom.trim() } }),
    onSuccess: () => {
      setNom("");
      rafraichir();
      qc.invalidateQueries({ queryKey: ["comptes"] });
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (!comptes.data) return <LignesSquelette n={6} />;
  const noms = Object.fromEntries(comptes.data.map((c) => [c.id, c.nom]));

  return (
    <div className="grid max-w-5xl gap-5 lg:grid-cols-[1fr_360px]">
      <div className="space-y-5">
        {comptes.data.map((c) => (
          <CarteCompte key={c.id} compte={c} onJeton={(valeur) => setJeton({ compte: c.nom, valeur })} />
        ))}
        <form
          className="flex flex-wrap items-end gap-2 rounded-xl border border-dashed p-4"
          onSubmit={(e) => {
            e.preventDefault();
            if (nom.trim()) creer.mutate();
          }}
        >
          <div className="min-w-48 flex-1 space-y-1">
            <label htmlFor="nouveau-compte" className="text-sm font-medium">
              Ajouter un compte Vinted sans boîte mail
            </label>
            <Input id="nouveau-compte" value={nom} onChange={(e) => setNom(e.target.value)} placeholder="Ex. : Sœur" />
          </div>
          <Button type="submit" disabled={!nom.trim() || creer.isPending}>
            <Plus /> Ajouter
          </Button>
        </form>
      </div>

      <section className="space-y-3 rounded-xl border bg-card p-4">
        <h2 className="text-sm font-semibold">Journal de l&apos;extension</h2>
        {!journal.data?.length ? (
          <p className="text-sm text-muted-foreground">Rien pour l&apos;instant.</p>
        ) : (
          <ol className="max-h-[560px] space-y-2 overflow-y-auto text-sm">
            {journal.data.map((j) => (
              <li key={j.id} className="border-l-2 pl-2" style={{ borderColor: "var(--border)" }}>
                <p
                  className={cn(
                    j.niveau === "erreur" && "text-destructive",
                    j.niveau === "alerte" && "text-amber-700 dark:text-amber-300",
                  )}
                >
                  {j.message}
                </p>
                <p className="text-xs text-muted-foreground tabular-nums">
                  {formatDateHeure(j.date)}
                  {j.compte_id && noms[j.compte_id] ? ` · ${noms[j.compte_id]}` : ""}
                </p>
              </li>
            ))}
          </ol>
        )}
      </section>

      <Dialog open={jeton !== null} onOpenChange={(o) => !o && setJeton(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Jeton d&apos;extension : {jeton?.compte}</DialogTitle>
            <DialogDescription>
              Colle-le dans les options de l&apos;extension, dans le profil Chrome de ce compte. Il ne sera plus jamais
              affiché ; l&apos;ancien jeton ne fonctionne plus.
            </DialogDescription>
          </DialogHeader>
          <code className="block rounded-md bg-muted p-3 text-xs break-all">{jeton?.valeur}</code>
          <Button onClick={() => jeton && copier(jeton.valeur, "Jeton")}>
            <Copy /> Copier le jeton
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function CarteCompte({ compte: c, onJeton }: { compte: CompteAutomatisation; onJeton: (v: string) => void }) {
  const qc = useQueryClient();
  const [identifiant, setIdentifiant] = useState("");
  const rafraichir = () => qc.invalidateQueries({ queryKey: ["automatisation"] });
  const action = useMutation({
    mutationFn: (a: { chemin: string; methode?: string; body?: unknown }) =>
      api<unknown>(`/automatisation/comptes/${c.id}${a.chemin}`, { method: a.methode ?? "POST", body: a.body }),
    onSuccess: (r, a) => {
      rafraichir();
      if (a.chemin === "/jeton") onJeton((r as { jeton: string }).jeton);
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const enLigne = c.extension_vue_le !== null && Date.now() - new Date(c.extension_vue_le).getTime() < EN_LIGNE_MS;
  const mauvaisCompte =
    c.vinted_user_id !== null && c.vinted_user_id_vu !== null && c.vinted_user_id !== c.vinted_user_id_vu;

  return (
    <section className="space-y-4 rounded-xl border bg-card p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold">{c.nom}</h2>
          <p className="text-xs text-muted-foreground">
            {c.imap_configure ? "Boîte mail branchée" : "Sans boîte mail"} · Brouillons aujourd&apos;hui :{" "}
            {c.brouillons_du_jour}/{c.brouillons_max_jour}
          </p>
        </div>
        <Button
          variant={c.pause ? "default" : "outline"}
          size="sm"
          disabled={action.isPending}
          onClick={() => action.mutate({ chemin: c.pause ? "/reprendre" : "/pause" })}
        >
          {c.pause ? <Play /> : <Pause />}
          {c.pause ? "Reprendre" : "Mettre en pause"}
        </Button>
      </div>

      {c.pause && (
        <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          En pause : {c.pause_raison ?? "aucune action sur Vinted"}. Les tâches restent en file.
        </p>
      )}

      <dl className="grid gap-x-4 gap-y-2 text-sm sm:grid-cols-[180px_1fr]">
        <dt className="text-muted-foreground">Extension</dt>
        <dd className="flex items-center gap-2">
          <span className={cn("size-2 rounded-full", enLigne ? "bg-emerald-500" : "bg-muted-foreground/40")} />
          {c.extension_vue_le
            ? `${enLigne ? "En ligne" : "Hors ligne"} · vue le ${formatDateHeure(c.extension_vue_le)}${c.extension_version ? ` · v${c.extension_version}` : ""}`
            : c.jeton_defini
              ? "Jamais connectée"
              : "Pas encore de jeton"}
        </dd>
        <dt className="text-muted-foreground">Compte Vinted attendu</dt>
        <dd className="space-y-2">
          <p className="tabular-nums">{c.vinted_user_id ?? "non défini : aucune action tant qu'il manque"}</p>
          {c.vinted_user_id_vu !== null && c.vinted_user_id_vu !== c.vinted_user_id && (
            <div
              className={cn(
                "flex flex-wrap items-center gap-2 rounded-lg px-3 py-2 text-sm",
                mauvaisCompte
                  ? "bg-red-50 text-red-800 dark:bg-red-950/40 dark:text-red-300"
                  : "bg-muted text-foreground",
              )}
            >
              {mauvaisCompte && <ShieldAlert className="size-4" />}
              Connecté dans le profil : {c.vinted_login_vu ?? "?"} ({c.vinted_user_id_vu})
              <Button
                size="xs"
                variant="outline"
                onClick={() => action.mutate({ chemin: "", methode: "PATCH", body: { confirmer_compte_vu: true } })}
              >
                <CheckCircle2 /> C&apos;est bien ce compte
              </Button>
            </div>
          )}
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              const n = Number(identifiant);
              if (Number.isInteger(n) && n > 0) {
                action.mutate({ chemin: "", methode: "PATCH", body: { vinted_user_id: n } });
                setIdentifiant("");
              }
            }}
          >
            <Input
              value={identifiant}
              onChange={(e) => setIdentifiant(e.target.value.replace(/\D/g, ""))}
              placeholder="Identifiant Vinted (chiffres)"
              inputMode="numeric"
              className="h-8 max-w-56"
              aria-label="Identifiant Vinted attendu"
            />
            <Button type="submit" size="sm" variant="outline" disabled={!identifiant}>
              Enregistrer
            </Button>
          </form>
        </dd>
        <dt className="text-muted-foreground">Jeton d&apos;extension</dt>
        <dd>
          <Button
            size="sm"
            variant="outline"
            disabled={action.isPending}
            onClick={() =>
              (!c.jeton_defini || confirm("Générer un nouveau jeton ? L'ancien cessera de fonctionner.")) &&
              action.mutate({ chemin: "/jeton" })
            }
          >
            {action.isPending ? <Loader2 className="animate-spin" /> : <KeyRound />}
            {c.jeton_defini ? "Générer un nouveau jeton" : "Générer un jeton d'extension"}
          </Button>
        </dd>
      </dl>
    </section>
  );
}
