"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, Layers, Loader2, Shirt } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { StatutBadge } from "@/components/commun";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import { formatEuros, saisieVersDecimal } from "@/lib/format";
import { useBatches, useInvaliderStock } from "@/lib/queries";
import type { Article, Correspondance } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Résumé de la provenance une fois choisie. */
export function ResumeProvenance({ article, onModifier }: { article: Article; onModifier: () => void }) {
  return (
    <p className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
      {article.perso ? (
        <span className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 font-medium text-foreground">
          <Shirt className="size-3.5" /> Pièce perso · coût 0 €
        </span>
      ) : (
        <span className="inline-flex items-center gap-1 rounded-md bg-muted px-2 py-0.5 font-medium text-foreground">
          <Layers className="size-3.5" /> {article.batch_nom ?? "Sans batch"} · achat{" "}
          {formatEuros(article.prix_achat_net)}
        </span>
      )}
      <Button variant="link" size="sm" className="h-auto p-0" onClick={onModifier}>
        Modifier
      </Button>
    </p>
  );
}

/**
 * D'où vient l'article : un article déjà dans le stock (import Excel, batch), un nouvel article d'un batch,
 * ou une pièce perso (coût 0 €, hors batchs). Choisir un article du stock fusionne l'annonce avec lui.
 */
export function ChoixProvenance({ article, onChoisi }: { article: Article; onChoisi: (articleId: number) => void }) {
  const invalider = useInvaliderStock();
  const { data: batches } = useBatches();
  const suggestions = useQuery({
    queryKey: ["annonce", article.id, "correspondances"],
    queryFn: () => api<Correspondance[]>(`/annonces/${article.id}/correspondances`),
  });
  const [batch, setBatch] = useState(article.batch_id ? String(article.batch_id) : "");
  const [prixAchat, setPrixAchat] = useState(
    article.prix_achat_net && !article.perso ? String(Number(article.prix_achat_net)).replace(".", ",") : "",
  );

  const choix = useMutation({
    mutationFn: (corps: {
      mode: "stock" | "batch" | "perso";
      article_stock_id?: number;
      batch_id?: number | null;
      prix_achat?: string | null;
    }) => api<{ article_id: number }>(`/annonces/${article.id}/provenance`, { body: corps }),
    onSuccess: (r, corps) => {
      invalider();
      toast.success(
        corps.mode === "stock"
          ? "Annonce rattachée à l'article du stock"
          : corps.mode === "perso"
            ? "Pièce perso : coût 0 €"
            : "Article rattaché au batch",
      );
      onChoisi(r.article_id);
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const prixValide = !prixAchat || saisieVersDecimal(prixAchat) !== null;

  return (
    <section className="space-y-4 rounded-xl border border-brand/40 bg-brand-soft/20 p-4 md:p-5">
      <div>
        <h2 className="text-sm font-semibold">D&apos;où vient cet article ?</h2>
        <p className="text-xs text-muted-foreground">
          Pour compter la marge au bon endroit. Une pièce perso est comptée à 0 € d&apos;achat et reste hors des batchs.
        </p>
      </div>

      {!!suggestions.data?.length && (
        <div className="space-y-1.5">
          <p className="text-sm font-medium">C&apos;est un article de ton stock ?</p>
          {suggestions.data.map((s) => (
            <button
              key={s.id}
              type="button"
              disabled={choix.isPending}
              onClick={() => choix.mutate({ mode: "stock", article_stock_id: s.id })}
              className="flex w-full items-center gap-3 rounded-lg border bg-card px-3 py-2.5 text-left text-sm outline-none hover:border-brand hover:bg-brand-soft/40 focus-visible:ring-3 focus-visible:ring-ring/50"
            >
              <span className="min-w-0 flex-1">
                <span className="block truncate font-medium">
                  {s.nom}
                  {s.taille && <span className="font-normal text-muted-foreground"> · {s.taille}</span>}
                </span>
                <span className="text-xs text-muted-foreground">
                  {[s.batch_nom, `achat ${formatEuros(s.prix_achat_net)}`].filter(Boolean).join(" · ")}
                </span>
              </span>
              <StatutBadge statut={s.statut} />
              <Check className="size-4 text-brand" />
            </button>
          ))}
        </div>
      )}

      <div className={cn("grid gap-3 sm:grid-cols-2", !!suggestions.data?.length && "border-t pt-4")}>
        <div className="space-y-2 rounded-lg border bg-card p-3">
          <p className="flex items-center gap-1.5 text-sm font-medium">
            <Layers className="size-4" /> Nouvel article d&apos;un batch
          </p>
          <div className="grid grid-cols-[1fr_110px] gap-2">
            <Select value={batch} onValueChange={setBatch}>
              <SelectTrigger className="w-full" aria-label="Batch">
                <SelectValue placeholder="Choisir le batch" />
              </SelectTrigger>
              <SelectContent>
                {batches?.map((b) => (
                  <SelectItem key={b.id} value={String(b.id)}>
                    {b.nom}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Input
              inputMode="decimal"
              placeholder="Achat €"
              aria-label="Prix d'achat"
              aria-invalid={!prixValide}
              value={prixAchat}
              onChange={(e) => setPrixAchat(e.target.value)}
            />
          </div>
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            disabled={!batch || !prixValide || choix.isPending}
            onClick={() =>
              choix.mutate({ mode: "batch", batch_id: Number(batch), prix_achat: saisieVersDecimal(prixAchat) })
            }
          >
            Rattacher au batch
          </Button>
        </div>
        <div className="flex flex-col justify-between gap-2 rounded-lg border bg-card p-3">
          <div>
            <p className="flex items-center gap-1.5 text-sm font-medium">
              <Shirt className="size-4" /> Pièce perso
            </p>
            <p className="text-xs text-muted-foreground">Une de tes affaires : achat compté 0 €.</p>
          </div>
          <Button
            variant="outline"
            size="sm"
            className="w-full"
            disabled={choix.isPending}
            onClick={() => choix.mutate({ mode: "perso" })}
          >
            {choix.isPending && <Loader2 className="animate-spin" />}
            C&apos;est une pièce perso
          </Button>
        </div>
      </div>
    </section>
  );
}
