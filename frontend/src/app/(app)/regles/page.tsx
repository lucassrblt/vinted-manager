"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Filter, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { EnTetePage, EtatVide, LignesSquelette, MessageErreur } from "@/components/commun";
import { type BrouillonRegle, EditeurRegle, REGLE_VIDE } from "@/components/mails/editeur-regle";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { TYPES_EMAIL } from "@/lib/statuts";
import type { Regle } from "@/lib/types";
import { cn } from "@/lib/utils";

export default function PageRegles() {
  const qc = useQueryClient();
  const [edition, setEdition] = useState<BrouillonRegle | null>(null);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["regles"],
    queryFn: () => api<Regle[]>("/regles"),
  });

  const basculer = useMutation({
    mutationFn: (r: Regle) =>
      api<Regle>(`/regles/${r.id}`, {
        method: "PUT",
        body: {
          nom: r.nom,
          type_cible: r.type_cible,
          conditions: r.conditions,
          extraction: r.extraction,
          priorite: r.priorite,
          active: !r.active,
        },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["regles"] }),
    onError: (e: Error) => toast.error(e.message),
  });
  const supprimer = useMutation({
    mutationFn: (id: number) => api(`/regles/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["regles"] });
      toast.success("Règle supprimée");
    },
  });

  return (
    <>
      <EnTetePage
        titre="Règles des mails"
        description="Testées par priorité croissante : la première qui correspond donne le type du mail."
        actions={
          <Button onClick={() => setEdition({ ...REGLE_VIDE })}>
            <Plus /> Nouvelle règle
          </Button>
        }
      />
      {error ? (
        <MessageErreur erreur={error} reessayer={() => refetch()} />
      ) : isLoading ? (
        <LignesSquelette />
      ) : !data?.length ? (
        <EtatVide
          icone={Filter}
          titre="Aucune règle"
          texte="Les règles initiales sont installées au premier démarrage du serveur."
        />
      ) : (
        <ul className="divide-y rounded-xl border bg-card">
          {data.map((r) => (
            <li key={r.id} className={cn("flex flex-wrap items-center gap-3 px-4 py-3", !r.active && "opacity-55")}>
              <span className="w-10 text-sm text-muted-foreground tabular-nums">{r.priorite}</span>
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{r.nom}</p>
                <p className="truncate text-xs text-muted-foreground">
                  {TYPES_EMAIL[r.type_cible]}
                  {r.conditions.sujet_contient?.length ? ` · sujet : ${r.conditions.sujet_contient.join(", ")}` : ""}
                  {Object.keys(r.extraction).length ? ` · extrait : ${Object.keys(r.extraction).join(", ")}` : ""}
                </p>
              </div>
              <Switch checked={r.active} onCheckedChange={() => basculer.mutate(r)} aria-label={`Activer ${r.nom}`} />
              <Button variant="ghost" size="icon-sm" aria-label="Modifier" onClick={() => setEdition(r)}>
                <Pencil />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Supprimer"
                onClick={() => confirm(`Supprimer la règle « ${r.nom} » ?`) && supprimer.mutate(r.id)}
              >
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      )}
      {edition && <EditeurRegle ouvert={!!edition} setOuvert={(v) => !v && setEdition(null)} initiale={edition} />}
    </>
  );
}
