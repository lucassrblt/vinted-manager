"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowDownRight, ArrowUpRight, Clock, PackageOpen, Target, Truck } from "lucide-react";
import Link from "next/link";

import { CarteKpi, GrilleSquelette, MessageErreur } from "@/components/commun";
import { Progress } from "@/components/ui/progress";
import { api } from "@/lib/api";
import { formatEuros, num } from "@/lib/format";
import type { EcranDuJour } from "@/lib/types";
import { cn } from "@/lib/utils";

function Evolution({ actuel, precedent }: { actuel: number; precedent: number }) {
  if (precedent === 0) return <span>semaine précédente : 0</span>;
  const delta = (actuel - precedent) / precedent;
  const Icone = delta >= 0 ? ArrowUpRight : ArrowDownRight;
  return (
    <span
      className={cn("inline-flex items-center gap-0.5", delta >= 0 ? "text-brand" : "text-red-600 dark:text-red-400")}
    >
      <Icone className="size-3.5" />
      {Math.abs(Math.round(delta * 100))} % vs semaine précédente
    </span>
  );
}

function salutation() {
  const heure = new Intl.DateTimeFormat("fr-FR", { timeZone: "Europe/Paris", hour: "2-digit", hourCycle: "h23" })
    .formatToParts(new Date())
    .find((p) => p.type === "hour")?.value;
  return Number(heure) < 18 ? "Bonjour" : "Bonsoir";
}

export default function EcranDuJourPage() {
  const {
    data: d,
    error,
    refetch,
  } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api<EcranDuJour>("/dashboard/jour"),
    refetchInterval: 120_000,
  });
  const date = new Intl.DateTimeFormat("fr-FR", {
    timeZone: "Europe/Paris",
    weekday: "long",
    day: "numeric",
    month: "long",
  }).format(new Date());

  if (error) return <MessageErreur erreur={error} reessayer={() => refetch()} />;

  return (
    <div className="space-y-6">
      <div>
        <p className="text-sm text-muted-foreground first-letter:uppercase">{date}</p>
        <h1 className="text-2xl font-semibold tracking-tight">{salutation()}</h1>
      </div>

      {!d ? (
        <GrilleSquelette n={8} />
      ) : (
        <>
          <div className="rounded-xl border bg-card p-4">
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2 text-sm font-medium">
                <Target className="size-4 text-brand" /> Objectif du jour
              </span>
              <span className="text-sm tabular-nums">
                <span className="text-lg font-semibold">{d.objectif_jour.ventes}</span>
                <span className="text-muted-foreground"> / {d.objectif_jour.objectif} ventes</span>
              </span>
            </div>
            <Progress
              value={
                d.objectif_jour.objectif ? Math.min(100, (d.objectif_jour.ventes / d.objectif_jour.objectif) * 100) : 0
              }
              className="mt-3 h-2 [&>div]:bg-brand"
              aria-label="Progression de l'objectif du jour"
            />
          </div>

          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <CarteKpi
              libelle="Articles reçus à publier"
              valeur={d.a_publier}
              icone={PackageOpen}
              href="/stock?statut=recu_a_publier"
              detail={d.a_publier ? "à mettre en ligne" : "rien en attente"}
            />
            <CarteKpi
              libelle="Commandes en attente"
              valeur={d.commandes_en_attente}
              icone={Truck}
              href="/stock?statut=commande"
              detail="pas encore reçues"
            />
            <CarteKpi
              libelle="Litiges ouverts"
              valeur={d.litiges}
              icone={AlertTriangle}
              href="/stock?statut=litige"
              ton={d.litiges ? "alerte" : undefined}
              detail={d.litiges ? "à traiter en priorité" : "aucun litige"}
            />
            <CarteKpi
              libelle={`En ligne depuis longtemps`}
              valeur={d.articles_lents.length}
              icone={Clock}
              href="#articles-lents"
              detail="à relancer ou baisser"
            />
          </div>

          <section>
            <h2 className="mb-3 text-sm font-semibold">Cette semaine</h2>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <CarteKpi
                libelle="CA"
                valeur={formatEuros(d.semaine.ca)}
                ton="brand"
                href="/compta"
                detail={<Evolution actuel={num(d.semaine.ca) ?? 0} precedent={num(d.semaine.ca_precedente) ?? 0} />}
              />
              <CarteKpi
                libelle="Marge"
                valeur={formatEuros(d.semaine.marge)}
                href="/compta"
                detail={
                  <Evolution actuel={num(d.semaine.marge) ?? 0} precedent={num(d.semaine.marge_precedente) ?? 0} />
                }
              />
              <CarteKpi
                libelle="Ventes"
                valeur={d.semaine.nb_ventes}
                href="/compta"
                detail={<Evolution actuel={d.semaine.nb_ventes} precedent={d.semaine.nb_ventes_precedente} />}
              />
            </div>
          </section>

          <section id="articles-lents" className="rounded-xl border bg-card">
            <div className="border-b px-4 py-3">
              <h2 className="text-sm font-semibold">Articles en ligne depuis longtemps</h2>
              <p className="text-xs text-muted-foreground">
                La suggestion de nouveau prix arrivera avec l&apos;étape 3.
              </p>
            </div>
            {d.articles_lents.length === 0 ? (
              <p className="px-4 py-6 text-center text-sm text-muted-foreground">Aucun article qui traîne.</p>
            ) : (
              <ul className="divide-y">
                {d.articles_lents.map((a) => (
                  <li key={a.id}>
                    <Link href={`/stock/${a.id}`} className="flex items-center gap-3 px-4 py-3 hover:bg-muted/50">
                      <span className="min-w-0 flex-1 truncate text-sm font-medium">
                        {a.nom}
                        {a.taille && <span className="font-normal text-muted-foreground"> · {a.taille}</span>}
                      </span>
                      <span className="text-sm tabular-nums">{formatEuros(a.prix_vente)}</span>
                      <span className="w-14 text-right text-xs text-amber-700 tabular-nums dark:text-amber-400">
                        {a.jours_en_ligne} j
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
