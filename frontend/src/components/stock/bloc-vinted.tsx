"use client";

import { useMutation } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { formatDateHeure, formatEuros } from "@/lib/format";
import { useInvaliderStock } from "@/lib/queries";
import type { Article } from "@/lib/types";

const LIBELLES_BROUILLON = {
  a_creer: "à créer",
  en_cours: "création en cours par l'extension",
  cree: "créé, à publier sur Vinted",
  erreur: "en erreur",
} as const;

/** Suivi Vinted de l'article : brouillon automatique, annonce, prix de référence des offres. */
export function BlocVinted({ article: a }: { article: Article }) {
  const invalider = useInvaliderStock();
  const relancer = useMutation({
    mutationFn: () => api(`/articles/${a.id}/brouillon/relancer`, { method: "POST" }),
    onSuccess: () => {
      invalider();
      toast.success("Brouillon remis dans la file");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const debloquer = useMutation({
    mutationFn: () => api(`/articles/${a.id}/republication/debloquer`, { method: "POST" }),
    onSuccess: () => {
      invalider();
      toast.success("Republication réautorisée");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const rien =
    !a.republication_bloquee &&
    !a.brouillon_statut &&
    !a.vinted_item_id &&
    !a.vinted_draft_id &&
    !a.prix_initial &&
    !a.couleur_a_verifier;
  if (rien) {
    return (
      <p className="text-sm text-muted-foreground">
        Pas encore sur Vinted. Un article reçu, attribué à un compte, avec son annonce, son prix et ses photos devient
        un brouillon automatiquement.
      </p>
    );
  }
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-sm">
      {a.importe_vinted && (
        <>
          <dt className="text-muted-foreground">Origine</dt>
          <dd>importé depuis le dressing Vinted</dd>
        </>
      )}
      {a.brouillon_statut && (
        <>
          <dt className="text-muted-foreground">Brouillon</dt>
          <dd>
            {LIBELLES_BROUILLON[a.brouillon_statut]}
            {a.brouillon_cree_le && a.brouillon_statut === "cree" && ` le ${formatDateHeure(a.brouillon_cree_le)}`}
          </dd>
        </>
      )}
      {a.brouillon_statut === "erreur" && (
        <dd className="col-span-2 space-y-2 rounded-lg bg-red-50 p-2 text-red-800 dark:bg-red-950/40 dark:text-red-300">
          <p>{a.brouillon_erreur}</p>
          <Button size="xs" variant="outline" disabled={relancer.isPending} onClick={() => relancer.mutate()}>
            <RotateCcw /> Relancer le brouillon
          </Button>
        </dd>
      )}
      {a.republication_bloquee && (
        <dd className="col-span-2 space-y-2 rounded-lg bg-red-50 p-2 text-red-800 dark:bg-red-950/40 dark:text-red-300">
          <p>
            La dernière republication a échoué : vérifie l&apos;annonce sur Vinted (doublon, brouillon restant) avant de
            la réautoriser.
          </p>
          <Button size="xs" variant="outline" disabled={debloquer.isPending} onClick={() => debloquer.mutate()}>
            <RotateCcw /> Réautoriser la republication
          </Button>
        </dd>
      )}
      {a.couleur_a_verifier && (
        <dd className="col-span-2 rounded-lg bg-amber-50 p-2 text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          Couleur d&apos;une photo retouchée à vérifier : brouillon bloqué jusqu&apos;à validation (voir les photos).
        </dd>
      )}
      {a.vinted_item_id && (
        <>
          <dt className="text-muted-foreground">Annonce</dt>
          <dd>
            <a
              href={`https://www.vinted.fr/items/${a.vinted_item_id}`}
              target="_blank"
              rel="noreferrer"
              className="underline underline-offset-2"
            >
              n° {a.vinted_item_id}
            </a>
          </dd>
        </>
      )}
      {(a.vinted_vues !== null || a.vinted_favoris !== null) && (
        <>
          <dt className="text-muted-foreground">Audience</dt>
          <dd className="tabular-nums">
            {a.vinted_vues ?? 0} vue(s) · {a.vinted_favoris ?? 0} favori(s)
          </dd>
        </>
      )}
      {a.republications > 0 && (
        <>
          <dt className="text-muted-foreground">Republiée</dt>
          <dd>
            {a.republications} fois, dernière le {formatDateHeure(a.derniere_publication_le)}
          </dd>
        </>
      )}
      {a.prix_avant_baisse && (
        <>
          <dt className="text-muted-foreground">Baisse auto</dt>
          <dd className="tabular-nums">
            {formatEuros(a.prix_avant_baisse)} → {formatEuros(a.prix_vente_cible)}
          </dd>
        </>
      )}
      {a.prix_initial && (
        <>
          <dt className="text-muted-foreground">Prix initial</dt>
          <dd className="tabular-nums">
            {formatEuros(a.prix_initial)} · plancher des offres {formatEuros(a.prix_plancher)}
          </dd>
        </>
      )}
    </dl>
  );
}
