"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatDateHeure } from "@/lib/format";
import type { SyncLog } from "@/lib/types";

export function BoutonSynchro() {
  const qc = useQueryClient();
  const journal = useQuery({ queryKey: ["imap", "logs"], queryFn: () => api<SyncLog[]>("/imap/logs") });
  const derniere = journal.data?.[0];
  const synchro = useMutation({
    mutationFn: () => api<SyncLog[]>("/imap/sync", { method: "POST" }),
    onSuccess: (journaux) => {
      qc.invalidateQueries();
      const nb = journaux.reduce((t, j) => t + j.nb_mails, 0);
      const erreurs = journaux.filter((j) => j.erreur && j.nb_mails === 0);
      for (const j of erreurs) toast.error(j.erreur, { duration: 8000 });
      if (nb || !erreurs.length) toast.success(nb ? `${nb} nouveau(x) mail(s)` : "Aucun nouveau mail");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  return (
    <div className="flex items-center gap-3">
      {derniere && (
        <span className="hidden text-xs text-muted-foreground sm:inline">
          {derniere.erreur ? (
            <span className="inline-flex items-center gap-1 text-red-600 dark:text-red-400" title={derniere.erreur}>
              <AlertCircle className="size-3.5" /> Dernière synchro en erreur
            </span>
          ) : (
            `Synchro : ${formatDateHeure(derniere.debut)}`
          )}
        </span>
      )}
      <Button variant="outline" onClick={() => synchro.mutate()} disabled={synchro.isPending}>
        {synchro.isPending ? <Loader2 className="animate-spin" /> : <RefreshCw />}
        Synchroniser maintenant
      </Button>
    </div>
  );
}
