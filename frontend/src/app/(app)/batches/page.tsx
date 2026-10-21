"use client";

import { Layers, Plus } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { EnTetePage, EtatVide, LignesSquelette, MessageErreur } from "@/components/commun";
import { DialogBatch } from "@/components/stock/dialog-batch";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatCoefficient, formatDate, formatDelai, formatEuros, formatPourcent, num } from "@/lib/format";
import { useBatches } from "@/lib/queries";

export default function PageBatches() {
  const { data, isLoading, error, refetch } = useBatches();
  const [dialog, setDialog] = useState(false);

  return (
    <>
      <EnTetePage
        titre="Batches"
        description="Performance de chaque commande fournisseur"
        actions={
          <Button onClick={() => setDialog(true)}>
            <Plus /> Ajouter un batch
          </Button>
        }
      />
      {error ? (
        <MessageErreur erreur={error} reessayer={() => refetch()} />
      ) : isLoading ? (
        <LignesSquelette n={5} />
      ) : !data?.length ? (
        <EtatVide
          icone={Layers}
          titre="Aucun batch"
          texte="Crée ton premier batch pour suivre une commande fournisseur et répartir sa remise."
          action={{ libelle: "Ajouter un batch", onClick: () => setDialog(true) }}
        />
      ) : (
        <>
          <div className="grid gap-3 md:hidden">
            {data.map((b) => (
              <Link key={b.id} href={`/batches/${b.id}`} className="rounded-xl border bg-card p-4 active:bg-muted">
                <div className="flex items-center justify-between">
                  <span className="font-medium">{b.nom}</span>
                  <span className="text-sm text-muted-foreground">{b.fournisseur}</span>
                </div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-sm tabular-nums">
                  <div>
                    <p className="text-xs text-muted-foreground">Vendus</p>
                    {b.nb_vendus}/{b.nb_articles}
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">CA</p>
                    {formatEuros(b.ca)}
                  </div>
                  <div>
                    <p className="text-xs text-muted-foreground">Marge</p>
                    {formatEuros(b.marge_realisee)}
                  </div>
                </div>
              </Link>
            ))}
          </div>
          <div className="hidden overflow-x-auto rounded-xl border bg-card md:block">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableHead>Batch</TableHead>
                  <TableHead className="text-right">Articles</TableHead>
                  <TableHead className="text-right">Publiés</TableHead>
                  <TableHead className="text-right">Vendus</TableHead>
                  <TableHead className="w-36">Sell-through</TableHead>
                  <TableHead className="text-right">CA</TableHead>
                  <TableHead className="text-right">Marge</TableHead>
                  <TableHead className="text-right">Coeff.</TableHead>
                  <TableHead className="text-right">Délai moyen</TableHead>
                  <TableHead className="text-right">Stock restant</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((b) => (
                  <TableRow key={b.id}>
                    <TableCell>
                      <Link href={`/batches/${b.id}`} className="font-medium hover:underline">
                        {b.nom}
                      </Link>
                      <p className="text-xs text-muted-foreground">
                        {[b.fournisseur, b.date_commande && formatDate(b.date_commande)].filter(Boolean).join(" · ")}
                      </p>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{b.nb_articles}</TableCell>
                    <TableCell className="text-right tabular-nums">{b.nb_publies}</TableCell>
                    <TableCell className="text-right tabular-nums">{b.nb_vendus}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Progress
                          value={Math.min(100, (num(b.sell_through) ?? 0) * 100)}
                          className="h-1.5 [&>div]:bg-brand"
                          aria-label="Sell-through"
                        />
                        <span className="w-10 text-right text-xs tabular-nums">{formatPourcent(b.sell_through)}</span>
                      </div>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{formatEuros(b.ca)}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatEuros(b.marge_realisee)}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatCoefficient(b.coefficient_ventes)}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatDelai(b.delai_moyen_heures)}</TableCell>
                    <TableCell className="text-right tabular-nums">{formatEuros(b.valeur_stock_restant)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        </>
      )}
      <DialogBatch ouvert={dialog} setOuvert={setDialog} />
    </>
  );
}
