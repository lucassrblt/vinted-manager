"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Receipt, Sparkles, Undo2, X } from "lucide-react";
import Link from "next/link";
import { toast } from "sonner";

import { EnTetePage, EtatVide, LignesSquelette, MessageErreur, StatutBadge } from "@/components/commun";
import { BadgeCompte } from "@/components/badge-compte";
import { SelecteurArticle } from "@/components/selecteur-article";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatDateHeure, formatEuros } from "@/lib/format";
import { useInvaliderStock } from "@/lib/queries";
import type { VenteAConfirmer, VenteListe } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function PageVentes() {
  const qc = useQueryClient();
  const invaliderStock = useInvaliderStock();
  const aConfirmer = useQuery({
    queryKey: ["ventes", "a-confirmer"],
    queryFn: () => api<VenteAConfirmer[]>("/ventes/a-confirmer"),
  });
  const ventes = useQuery({ queryKey: ["ventes", "liste"], queryFn: () => api<VenteListe[]>("/ventes") });
  const invalider = () => {
    qc.invalidateQueries({ queryKey: ["ventes"] });
    qc.invalidateQueries({ queryKey: ["envois"] });
    invaliderStock();
  };

  const confirmer = useMutation({
    mutationFn: (c: { email_id: number; article_id: number }) => api("/ventes/confirmer", { body: c }),
    onSuccess: () => {
      invalider();
      toast.success("Vente confirmée : l'envoi est créé");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const ignorer = useMutation({
    mutationFn: (emailId: number) => api(`/emails/${emailId}/classer`, { body: { type: null } }),
    onSuccess: () => {
      invalider();
      toast.success("Mail ignoré");
    },
  });
  const annuler = useMutation({
    mutationFn: (venteId: number) => api(`/ventes/${venteId}/annuler`, { method: "POST" }),
    onSuccess: () => {
      invalider();
      toast.success("Rapprochement annulé : la vente est revenue à confirmer");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const septJours = Date.now() - 7 * 86400_000;
  const autos = (ventes.data ?? []).filter(
    (v) => v.auto_rapproche && new Date(v.date_heure).getTime() >= septJours && v.article.statut === "vendu",
  );

  return (
    <>
      <EnTetePage titre="Ventes" description="Ventes détectées dans tes mails Vinted" />

      <section className="mb-8">
        <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
          Ventes à confirmer
          {!!aConfirmer.data?.length && (
            <span className="rounded-full bg-amber-500 px-1.5 text-xs text-white tabular-nums">
              {aConfirmer.data.length}
            </span>
          )}
        </h2>
        {aConfirmer.error ? (
          <MessageErreur erreur={aConfirmer.error} reessayer={() => aConfirmer.refetch()} />
        ) : aConfirmer.isLoading ? (
          <LignesSquelette n={2} />
        ) : !aConfirmer.data?.length ? (
          <p className="rounded-xl border border-dashed px-4 py-6 text-center text-sm text-muted-foreground">
            Rien à confirmer : toutes les ventes détectées sont rapprochées.
          </p>
        ) : (
          <ul className="space-y-3">
            {aConfirmer.data.map((v) => (
              <li key={v.email_id} className="rounded-xl border bg-card p-4">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="flex flex-wrap items-center gap-2 font-medium">
                      {v.donnees.titre_article ? `« ${v.donnees.titre_article} »` : v.sujet}
                      <BadgeCompte nom={v.compte} />
                    </p>
                    <p className="text-sm text-muted-foreground tabular-nums">
                      {[
                        v.donnees.prix && formatEuros(v.donnees.prix),
                        v.donnees.acheteur && `acheteur ${v.donnees.acheteur}`,
                        formatDateHeure(v.date),
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </div>
                  <Button variant="ghost" size="sm" onClick={() => ignorer.mutate(v.email_id)}>
                    <X /> Ignorer
                  </Button>
                </div>
                <div className="mt-3 space-y-1.5">
                  {v.candidats.map((c, i) => (
                    <button
                      key={c.article_id}
                      type="button"
                      disabled={confirmer.isPending}
                      onClick={() => confirmer.mutate({ email_id: v.email_id, article_id: c.article_id })}
                      className={cn(
                        "flex w-full items-center gap-3 rounded-lg border px-3 py-2.5 text-left text-sm transition-colors outline-none hover:border-brand hover:bg-brand-soft/40 focus-visible:ring-3 focus-visible:ring-ring/50",
                        i === 0 && "border-brand/40",
                      )}
                    >
                      <span className="min-w-0 flex-1 truncate">
                        {c.nom}
                        {c.taille && <span className="text-muted-foreground"> · {c.taille}</span>}
                      </span>
                      <span className="text-muted-foreground tabular-nums">{formatEuros(c.prix_vente)}</span>
                      <span
                        className={cn(
                          "w-12 text-right text-xs font-medium tabular-nums",
                          c.score >= 80 ? "text-brand" : "text-muted-foreground",
                        )}
                        title="Score de correspondance"
                      >
                        {Math.min(100, Math.round(c.score))} %
                      </span>
                      <Check className="size-4 text-brand" />
                    </button>
                  ))}
                  <div className="pt-1">
                    <SelecteurArticle
                      libelle={v.candidats.length ? "Un autre article…" : "Choisir l'article vendu…"}
                      statuts={["en_ligne", "recu_a_publier"]}
                      onChoix={(a) => confirmer.mutate({ email_id: v.email_id, article_id: a.id })}
                    />
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {autos.length > 0 && (
        <section className="mb-8">
          <h2 className="mb-1 flex items-center gap-2 text-sm font-semibold">
            <Sparkles className="size-4 text-brand" /> Rapprochées automatiquement
          </h2>
          <p className="mb-3 text-xs text-muted-foreground">
            Vérifie qu&apos;il s&apos;agit du bon article ; tu peux annuler.
          </p>
          <ul className="divide-y rounded-xl border bg-card">
            {autos.map((v) => (
              <li key={v.id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
                <Link href={`/stock/${v.article.id}`} className="min-w-0 flex-1 truncate font-medium hover:underline">
                  {v.article.nom}
                </Link>
                <span className="tabular-nums">{formatEuros(v.prix)}</span>
                <span className="text-muted-foreground tabular-nums">{formatDateHeure(v.date_heure)}</span>
                <Button variant="outline" size="sm" onClick={() => annuler.mutate(v.id)} disabled={annuler.isPending}>
                  <Undo2 /> Annuler
                </Button>
              </li>
            ))}
          </ul>
        </section>
      )}

      <section>
        <h2 className="mb-3 text-sm font-semibold">30 derniers jours</h2>
        {ventes.isLoading ? (
          <LignesSquelette n={4} />
        ) : !ventes.data?.length ? (
          <EtatVide
            icone={Receipt}
            titre="Aucune vente détectée"
            texte="Configure ta boîte mail dans les paramètres : les ventes Vinted arriveront ici automatiquement."
            action={{ libelle: "Configurer les mails", href: "/parametres?onglet=mails" }}
          />
        ) : (
          <ul className="divide-y rounded-xl border bg-card">
            {ventes.data.map((v) => (
              <li key={v.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-4 py-3 text-sm">
                <Link href={`/stock/${v.article.id}`} className="min-w-0 flex-1 truncate font-medium hover:underline">
                  {v.article.nom}
                </Link>
                <StatutBadge statut={v.article.statut} />
                <span className="w-20 text-right tabular-nums">{formatEuros(v.prix)}</span>
                <span className="text-muted-foreground tabular-nums">{formatDateHeure(v.date_heure)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
