"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronRight, ImagePlus, Megaphone } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { EnTetePage, EtatVide, LignesSquelette, MessageErreur } from "@/components/commun";
import { api } from "@/lib/api";
import { formatEuros } from "@/lib/format";
import type { Article } from "@/lib/types";

export default function PageAnnonces() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["articles", "a-publier"],
    queryFn: () => api<Article[]>("/annonces/a-publier"),
  });
  return (
    <>
      <EnTetePage
        titre="Annonces"
        description={data ? `${data.length} article(s) reçu(s) à mettre en ligne` : "Articles reçus à mettre en ligne"}
        actions={
          <Button asChild>
            <Link href="/annonces/nouvelle">
              <ImagePlus /> Nouvelle annonce
            </Link>
          </Button>
        }
      />
      {error ? (
        <MessageErreur erreur={error} reessayer={() => refetch()} />
      ) : isLoading ? (
        <LignesSquelette n={6} />
      ) : !data?.length ? (
        <EtatVide
          icone={Megaphone}
          titre="Rien à publier"
          texte="Les articles au statut « Reçu · à publier » apparaissent ici."
          action={{ libelle: "Voir le stock", href: "/stock" }}
        />
      ) : (
        <ul className="divide-y rounded-xl border bg-card">
          {data.map((a) => (
            <li key={a.id}>
              <Link href={`/annonces/${a.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-muted/50">
                <span className="min-w-0 flex-1">
                  <span className="block truncate font-medium">{a.nom}</span>
                  <span className="text-xs text-muted-foreground">
                    {[a.marque, a.taille, a.perso ? "pièce perso" : `achat ${formatEuros(a.prix_achat_net)}`]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </span>
                {a.titre_annonce && (
                  <span className="hidden rounded-full bg-brand-soft px-2 py-0.5 text-xs text-brand sm:inline">
                    Annonce rédigée
                  </span>
                )}
                <ChevronRight className="size-4 text-muted-foreground" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </>
  );
}
