"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { EnTetePage, EtatVide, LignesSquelette, MessageErreur } from "@/components/commun";
import { CelluleEditable } from "@/components/stock/cellule-editable";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api } from "@/lib/api";
import { formatCoefficient, formatEuros } from "@/lib/format";
import type { Piste } from "@/lib/types";
import { cn } from "@/lib/utils";

const PRIORITES: Record<string, string> = {
  "très haute": "bg-brand-soft text-brand",
  haute: "bg-brand-soft/60 text-brand",
  moyenne: "bg-muted text-muted-foreground",
};

const BASES: Record<string, string> = {
  "marque+categorie": "même marque et catégorie",
  marque: "même marque",
  categorie: "même catégorie",
};

export default function PageSourcing() {
  const qc = useQueryClient();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["sourcing"],
    queryFn: () => api<Piste[]>("/sourcing"),
  });
  const rafraichir = () => qc.invalidateQueries({ queryKey: ["sourcing"] });

  const modifier = useMutation({
    mutationFn: ({ id, ...champs }: { id: number; [champ: string]: string | number | null }) =>
      api<Piste>(`/sourcing/${id}`, { method: "PATCH", body: champs }),
    onSuccess: () => {
      rafraichir();
      toast.success("Piste mise à jour");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const creer = useMutation({
    mutationFn: () => api<Piste>("/sourcing", { body: { produit: "Nouvelle piste" } }),
    onSuccess: () => rafraichir(),
    onError: (e: Error) => toast.error(e.message),
  });
  const supprimer = useMutation({
    mutationFn: (id: number) => api(`/sourcing/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      rafraichir();
      toast.success("Piste supprimée");
    },
  });

  const champ = (p: Piste, cle: keyof Piste, libelle: string, montant = false) => (
    <CelluleEditable
      libelle={libelle}
      type={montant ? "montant" : "texte"}
      valeur={p[cle] as string | null}
      affichage={montant ? formatEuros(p[cle] as string | null) : undefined}
      onSave={(v) => {
        if (cle === "produit" && !v) return;
        modifier.mutate({ id: p.id, [cle]: v });
      }}
    />
  );

  return (
    <>
      <EnTetePage
        titre="Sourcing"
        description="Pistes de produits à tester, comparées à tes ventes réelles"
        actions={
          <Button onClick={() => creer.mutate()}>
            <Plus /> Ajouter une piste
          </Button>
        }
      />
      {error ? (
        <MessageErreur erreur={error} reessayer={() => refetch()} />
      ) : isLoading ? (
        <LignesSquelette />
      ) : !data?.length ? (
        <EtatVide
          icone={Search}
          titre="Aucune piste de sourcing"
          texte="Elles sont importées depuis les onglets « Sourcing » de ton Excel, ou ajoute-les à la main."
          action={{ libelle: "Importer l'Excel", href: "/import" }}
        />
      ) : (
        <div className="overflow-x-auto rounded-xl border bg-card">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead className="min-w-28">Marque</TableHead>
                <TableHead className="min-w-56">Produit</TableHead>
                <TableHead className="min-w-32">Catégorie</TableHead>
                <TableHead className="text-right">Achat max</TableHead>
                <TableHead className="text-right">Revente basse</TableHead>
                <TableHead className="text-right">Revente haute</TableHead>
                <TableHead>Priorité</TableHead>
                <TableHead className="min-w-52 border-l bg-brand-soft/30">Mes ventes réelles</TableHead>
                <TableHead className="min-w-56">Commentaire</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>{champ(p, "marque", "la marque")}</TableCell>
                  <TableCell>
                    {champ(p, "produit", "le produit")}
                    {p.mots_cles && (
                      <p className="truncate text-xs text-muted-foreground" title={p.mots_cles}>
                        {p.mots_cles}
                      </p>
                    )}
                  </TableCell>
                  <TableCell>{champ(p, "categorie", "la catégorie")}</TableCell>
                  <TableCell className="w-28">{champ(p, "achat_max", "l'achat max", true)}</TableCell>
                  <TableCell className="w-28">{champ(p, "revente_basse", "la revente basse", true)}</TableCell>
                  <TableCell className="w-28">{champ(p, "revente_haute", "la revente haute", true)}</TableCell>
                  <TableCell>
                    <CelluleEditable
                      libelle="la priorité"
                      valeur={p.priorite}
                      affichage={
                        p.priorite ? (
                          <span
                            className={cn(
                              "rounded-full px-2 py-0.5 text-xs font-medium",
                              PRIORITES[p.priorite.toLowerCase()] ?? "bg-muted",
                            )}
                          >
                            {p.priorite}
                          </span>
                        ) : undefined
                      }
                      onSave={(v) => modifier.mutate({ id: p.id, priorite: v })}
                    />
                  </TableCell>
                  <TableCell className="border-l bg-brand-soft/20 text-sm">
                    {p.perf_nb_ventes > 0 ? (
                      <Tooltip>
                        <TooltipTrigger className="text-left">
                          <span className="tabular-nums">
                            {p.perf_nb_ventes} vente(s) · {formatEuros(p.perf_prix_moyen)} ·{" "}
                            {formatCoefficient(p.perf_coefficient_moyen)}
                          </span>
                          <span className="block text-xs text-muted-foreground">
                            {p.perf_delai_moyen_jours !== null
                              ? `vendu en ${p.perf_delai_moyen_jours.toLocaleString("fr-FR", { maximumFractionDigits: 1 })} j en moyenne`
                              : "délai inconnu"}
                          </span>
                        </TooltipTrigger>
                        <TooltipContent>Basé sur : {BASES[p.perf_base ?? ""] ?? "—"}</TooltipContent>
                      </Tooltip>
                    ) : (
                      <span className="text-muted-foreground">Aucune vente similaire</span>
                    )}
                  </TableCell>
                  <TableCell className="max-w-72">{champ(p, "commentaire", "le commentaire")}</TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon-sm"
                      aria-label="Supprimer la piste"
                      onClick={() => confirm(`Supprimer « ${p.produit} » ?`) && supprimer.mutate(p.id)}
                    >
                      <Trash2 />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </>
  );
}
