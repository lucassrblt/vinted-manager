"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { CarteKpi, IndicateurBadge, LignesSquelette, MessageErreur, StatutBadge } from "@/components/commun";
import { ZonePreuves } from "@/components/stock/preuves";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api } from "@/lib/api";
import { formatCoefficient, formatDate, formatDelai, formatEuros, formatPourcent } from "@/lib/format";
import type { Article, BatchStats, Preuve } from "@/lib/types";

export default function FicheBatch() {
  const id = Number(useParams<{ id: string }>().id);
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["batch", id],
    queryFn: () => api<{ batch: BatchStats; articles: Article[]; preuves: Preuve[] }>(`/batches/${id}`),
  });

  if (error) return <MessageErreur erreur={error} reessayer={() => refetch()} />;
  if (isLoading || !data) return <LignesSquelette n={10} />;
  const { batch: b, articles, preuves } = data;

  return (
    <div className="space-y-6">
      <div>
        <Link
          href="/batches"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" /> Batches
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">{b.nom}</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          {[
            b.fournisseur,
            b.date_commande && `commandé le ${formatDate(b.date_commande)}`,
            `remise ${formatEuros(b.remise_globale)}`,
          ]
            .filter(Boolean)
            .join(" · ")}
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <CarteKpi libelle="Investi" valeur={formatEuros(b.investi)} detail={`${b.nb_articles} articles`} />
        <CarteKpi
          libelle="CA"
          valeur={formatEuros(b.ca)}
          detail={`${b.nb_vendus} vendus sur ${b.nb_publies} publiés`}
        />
        <CarteKpi
          libelle="Marge réalisée"
          valeur={formatEuros(b.marge_realisee)}
          detail={`coeff. ${formatCoefficient(b.coefficient_ventes)}`}
        />
        <CarteKpi
          libelle="Sell-through"
          valeur={formatPourcent(b.sell_through)}
          detail={`délai moyen ${formatDelai(b.delai_moyen_heures)} · stock ${formatEuros(b.valeur_stock_restant)}`}
        />
      </div>

      <section>
        <h2 className="mb-3 text-sm font-semibold">Articles</h2>
        <div className="overflow-x-auto rounded-xl border bg-card">
          <Table>
            <TableHeader>
              <TableRow className="bg-muted/40 hover:bg-muted/40">
                <TableHead>Article</TableHead>
                <TableHead>Taille</TableHead>
                <TableHead className="text-right">Brut</TableHead>
                <TableHead className="text-right">Remise</TableHead>
                <TableHead className="text-right">Net</TableHead>
                <TableHead className="text-right">Vente</TableHead>
                <TableHead>Coeff.</TableHead>
                <TableHead>Statut</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {articles.map((a) => (
                <TableRow key={a.id}>
                  <TableCell className="max-w-72 truncate">
                    <Link href={`/stock/${a.id}`} className="font-medium hover:underline">
                      {a.nom}
                    </Link>
                  </TableCell>
                  <TableCell>{a.taille ?? "—"}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatEuros(a.prix_achat_brut)}</TableCell>
                  <TableCell className="text-right text-muted-foreground tabular-nums">
                    {formatEuros(a.remise)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{formatEuros(a.prix_achat_net)}</TableCell>
                  <TableCell className="text-right tabular-nums">{formatEuros(a.prix_vente)}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1.5">
                      <span className="tabular-nums">{formatCoefficient(a.coefficient)}</span>
                      <IndicateurBadge indicateur={a.indicateur} />
                    </div>
                  </TableCell>
                  <TableCell>
                    <StatutBadge statut={a.statut} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </section>

      <section className="max-w-2xl">
        <h2 className="mb-3 text-sm font-semibold">Preuves d&apos;achat du batch</h2>
        <ZonePreuves cible={{ batch_id: id }} preuves={preuves} onChange={() => refetch()} />
      </section>
    </div>
  );
}
