"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, X } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { formatDateHeure } from "@/lib/format";
import type { TacheVinted } from "@/lib/types";

export const LIBELLES_TACHES: Record<string, string> = {
  brouillon: "Brouillon",
  repondre_message: "Réponse à un message",
  accepter_offre: "Accepter une offre",
  refuser_offre: "Refuser une offre",
  contre_offre: "Contre-offre",
  relance_favori: "Relance d'un favori",
  republication: "Republication",
  modifier_prix: "Baisse de prix",
  message_apres_vente: "Message après-vente",
  photos_reference: "Photos de référence",
};

/** Tâches en attente : celles que l'assistant soumet à Lucas, puis la file à venir. */
export function FileTaches({ noms }: { noms: Record<number, string> }) {
  const { data } = useQuery({
    queryKey: ["automatisation", "taches", "attente"],
    queryFn: () =>
      api<TacheVinted[]>("/automatisation/taches", { params: { statut: ["a_valider", "a_faire", "en_cours"] } }),
    refetchInterval: 30_000,
  });
  if (!data?.length) return <p className="text-sm text-muted-foreground">Aucune action en attente.</p>;
  const tri = [...data].sort((a, b) => Number(b.statut === "a_valider") - Number(a.statut === "a_valider"));
  return (
    <ul className="space-y-2">
      {tri.map((t) => (
        <LigneTache key={t.id} tache={t} compte={noms[t.compte_id]} />
      ))}
    </ul>
  );
}

function LigneTache({ tache: t, compte }: { tache: TacheVinted; compte?: string }) {
  const qc = useQueryClient();
  const texteInitial = typeof t.payload.texte === "string" ? t.payload.texte : "";
  const [texte, setTexte] = useState(texteInitial);
  const action = useMutation({
    mutationFn: (quoi: "valider" | "annuler") =>
      api(`/automatisation/taches/${t.id}/${quoi}`, {
        method: "POST",
        body: quoi === "valider" && texte && texte !== texteInitial ? { texte } : {},
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["automatisation"] }),
    onError: (e: Error) => toast.error(e.message),
  });
  const raison = typeof t.payload.raison_escalade === "string" ? t.payload.raison_escalade : null;
  return (
    <li className="space-y-2 rounded-lg border p-3 text-sm">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="font-medium">
          {LIBELLES_TACHES[t.type] ?? t.type}
          {compte && <span className="font-normal text-muted-foreground"> · {compte}</span>}
        </p>
        <p className="text-xs text-muted-foreground tabular-nums">
          {t.statut === "a_valider"
            ? "à valider"
            : t.statut === "en_cours"
              ? "en cours"
              : `prévue le ${formatDateHeure(t.executer_apres)}`}
        </p>
      </div>
      {raison && <p className="text-amber-800 dark:text-amber-300">{raison}</p>}
      {t.statut === "a_valider" && typeof t.payload.texte === "string" && (
        <Textarea rows={3} value={texte} onChange={(e) => setTexte(e.target.value)} aria-label="Réponse proposée" />
      )}
      {t.statut !== "en_cours" && (
        <div className="flex gap-2">
          {t.statut === "a_valider" && (
            <Button size="xs" disabled={action.isPending} onClick={() => action.mutate("valider")}>
              <Check /> Envoyer
            </Button>
          )}
          <Button size="xs" variant="outline" disabled={action.isPending} onClick={() => action.mutate("annuler")}>
            <X /> {t.statut === "a_valider" ? "Ignorer" : "Annuler"}
          </Button>
        </div>
      )}
    </li>
  );
}
