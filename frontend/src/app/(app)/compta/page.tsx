"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart3, Download, Info } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { BarresHorizontales, GraphiqueCaMarge, Legende } from "@/components/charts";
import { CarteKpi, EnTetePage, EtatVide, GrilleSquelette, MessageErreur } from "@/components/commun";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, telecharger } from "@/lib/api";
import { aujourdhuiParis, formatCoefficient, formatDelai, formatEuros, formatPourcent, num } from "@/lib/format";
import type { Kpis, LigneRepartition, PointSerie } from "@/lib/types";

type Periode = "tout" | "semaine" | "mois" | "trimestre" | "annee" | "perso";

function bornes(periode: Periode, du: string, au: string): { du?: string; au?: string } {
  const auj = aujourdhuiParis();
  const [a, m, j] = auj.split("-").map(Number);
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  const jour = new Date(Date.UTC(a, m - 1, j));
  switch (periode) {
    case "semaine": {
      const debut = new Date(jour);
      debut.setUTCDate(jour.getUTCDate() - ((jour.getUTCDay() + 6) % 7));
      return { du: iso(debut), au: auj };
    }
    case "mois":
      return { du: `${a}-${String(m).padStart(2, "0")}-01`, au: auj };
    case "trimestre": {
      const mDebut = Math.floor((m - 1) / 3) * 3 + 1;
      return { du: `${a}-${String(mDebut).padStart(2, "0")}-01`, au: auj };
    }
    case "annee":
      return { du: `${a}-01-01`, au: auj };
    case "perso":
      return { du: du || undefined, au: au || undefined };
    default:
      return {};
  }
}

export default function PageCompta() {
  const [periode, setPeriode] = useState<Periode>("tout");
  const [du, setDu] = useState("");
  const [au, setAu] = useState("");
  const [granularite, setGranularite] = useState<"semaine" | "mois">("semaine");
  const [moisUrssaf, setMoisUrssaf] = useState(aujourdhuiParis().slice(0, 7));
  const params = useMemo(() => bornes(periode, du, au), [periode, du, au]);

  const kpis = useQuery({ queryKey: ["compta", "kpis", params], queryFn: () => api<Kpis>("/compta/kpis", { params }) });
  const series = useQuery({
    queryKey: ["compta", "series", granularite, params],
    queryFn: () => api<PointSerie[]>("/compta/series", { params: { granularite, ...params } }),
  });
  const repartition = useQuery({
    queryKey: ["compta", "repartition", params],
    queryFn: () =>
      api<{ marques: LigneRepartition[]; categories: LigneRepartition[] }>("/compta/repartition", { params }),
  });

  const k = kpis.data;

  return (
    <>
      <EnTetePage
        titre="Compta"
        description="Chiffre d'affaires, marges et cotisations estimées"
        actions={
          <div className="flex items-center gap-2">
            <Input
              type="month"
              value={moisUrssaf}
              onChange={(e) => setMoisUrssaf(e.target.value)}
              className="h-8 w-40"
              aria-label="Mois de la déclaration URSSAF"
            />
            <Button
              variant="outline"
              onClick={() =>
                telecharger("/compta/urssaf.csv", { mois: moisUrssaf }).catch((e) => toast.error(e.message))
              }
            >
              <Download /> CSV URSSAF
            </Button>
          </div>
        }
      />

      <div className="mb-5 flex flex-wrap items-center gap-2">
        <Tabs value={periode} onValueChange={(v) => setPeriode(v as Periode)}>
          <TabsList>
            <TabsTrigger value="tout">Tout</TabsTrigger>
            <TabsTrigger value="semaine">Semaine</TabsTrigger>
            <TabsTrigger value="mois">Mois</TabsTrigger>
            <TabsTrigger value="trimestre">Trimestre</TabsTrigger>
            <TabsTrigger value="annee">Année</TabsTrigger>
            <TabsTrigger value="perso">Personnalisé</TabsTrigger>
          </TabsList>
        </Tabs>
        {periode === "perso" && (
          <div className="flex items-center gap-2">
            <Input
              type="date"
              value={du}
              onChange={(e) => setDu(e.target.value)}
              className="h-8 w-40"
              aria-label="Du"
            />
            <span className="text-sm text-muted-foreground">au</span>
            <Input
              type="date"
              value={au}
              onChange={(e) => setAu(e.target.value)}
              className="h-8 w-40"
              aria-label="Au"
            />
          </div>
        )}
      </div>

      {kpis.error ? (
        <MessageErreur erreur={kpis.error} reessayer={() => kpis.refetch()} />
      ) : !k ? (
        <GrilleSquelette n={8} />
      ) : (
        <div className="space-y-6">
          {k.ventes_sans_date > 0 && (
            <p className="flex items-start gap-2 rounded-lg bg-muted/60 px-3 py-2 text-sm text-muted-foreground">
              <Info className="mt-0.5 size-4 shrink-0" />
              {k.ventes_sans_date} vente(s) importée(s) de l&apos;Excel n&apos;ont pas de date : elles ne comptent que
              dans la vue « Tout ».
            </p>
          )}

          <section>
            <h2 className="mb-3 text-sm font-semibold">
              Ventes {periode === "tout" ? "(depuis le début)" : "de la période"}
            </h2>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <CarteKpi
                libelle="CA encaissé"
                valeur={formatEuros(k.ca_encaisse)}
                detail={`${k.nb_ventes} vente(s)`}
                ton="brand"
              />
              <CarteKpi
                libelle="Marge réalisée"
                valeur={formatEuros(k.marge_realisee)}
                detail="sur les articles vendus"
              />
              <CarteKpi
                libelle="Cotisations estimées"
                valeur={formatEuros(k.cotisations_estimees)}
                detail={`${formatPourcent(k.taux_cotisations)} du CA`}
              />
              <CarteKpi
                libelle="Marge après cotisations"
                valeur={formatEuros(k.marge_apres_cotisations)}
                detail={`délai moyen de vente ${formatDelai(k.delai_moyen_heures)}`}
              />
            </div>
          </section>

          <section>
            <h2 className="mb-3 text-sm font-semibold">Stock et rentabilité globale (à date)</h2>
            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
              <CarteKpi libelle="Total investi" valeur={formatEuros(k.total_investi)} detail="vendu + stock" />
              <CarteKpi
                libelle="Valeur du stock non vendu"
                valeur={formatEuros(k.valeur_stock)}
                detail={`${k.nb_en_stock} article(s)`}
              />
              <CarteKpi
                libelle="Coefficient CA / investi"
                valeur={formatCoefficient(k.coefficient_global)}
                detail={`marge stock inclus ${formatEuros(k.marge_globale)}`}
              />
              <CarteKpi libelle="Sell-through" valeur={formatPourcent(k.sell_through)} detail="vendus / publiés" />
            </div>
            <div className="mt-3 grid grid-cols-3 gap-3 rounded-xl border bg-card p-4 text-sm sm:grid-cols-6">
              {[
                ["Total", k.nb_total],
                ["Vendus", k.nb_vendus],
                ["En stock", k.nb_en_stock],
                ["Reçus", k.nb_recus],
                ["Publiés", k.nb_publies],
                ["À publier", k.nb_a_publier],
              ].map(([l, v]) => (
                <div key={l}>
                  <p className="text-xs text-muted-foreground">{l}</p>
                  <p className="text-lg font-semibold tabular-nums">{v}</p>
                </div>
              ))}
            </div>
          </section>

          <section className="rounded-xl border bg-card p-4 md:p-5">
            <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 className="text-sm font-semibold">CA et marge</h2>
                <Legende
                  series={[
                    { libelle: "CA", couleur: "var(--chart-1)" },
                    { libelle: "Marge", couleur: "var(--chart-2)" },
                  ]}
                />
              </div>
              <Tabs value={granularite} onValueChange={(v) => setGranularite(v as "semaine" | "mois")}>
                <TabsList>
                  <TabsTrigger value="semaine">Par semaine</TabsTrigger>
                  <TabsTrigger value="mois">Par mois</TabsTrigger>
                </TabsList>
              </Tabs>
            </div>
            {series.data && series.data.length > 0 ? (
              <GraphiqueCaMarge
                donnees={series.data.map((p) => ({ periode: p.periode, ca: num(p.ca) ?? 0, marge: num(p.marge) ?? 0 }))}
              />
            ) : (
              <EtatVide
                icone={BarChart3}
                titre="Pas encore de ventes datées"
                texte="Les ventes avec une date apparaîtront ici."
              />
            )}
          </section>

          <div className="grid gap-5 lg:grid-cols-2">
            <section className="rounded-xl border bg-card p-4 md:p-5">
              <h2 className="mb-4 text-sm font-semibold">CA par marque</h2>
              <BarresHorizontales
                libelleSerie="CA"
                format={formatEuros}
                donnees={(repartition.data?.marques ?? [])
                  .slice(0, 10)
                  .map((l) => ({ cle: l.cle, valeur: num(l.ca) ?? 0 }))}
              />
            </section>
            <section className="rounded-xl border bg-card p-4 md:p-5">
              <h2 className="mb-4 text-sm font-semibold">CA par catégorie</h2>
              <BarresHorizontales
                libelleSerie="CA"
                format={formatEuros}
                donnees={(repartition.data?.categories ?? [])
                  .slice(0, 10)
                  .map((l) => ({ cle: l.cle, valeur: num(l.ca) ?? 0 }))}
              />
            </section>
            <section className="rounded-xl border bg-card p-4 md:p-5 lg:col-span-2">
              <h2 className="mb-1 text-sm font-semibold">Délai moyen de vente par catégorie</h2>
              <p className="mb-4 text-xs text-muted-foreground">Entre la publication et la vente.</p>
              {(repartition.data?.categories ?? []).some((l) => l.delai_moyen_heures !== null) ? (
                <BarresHorizontales
                  libelleSerie="Délai moyen"
                  format={(h) => formatDelai(h)}
                  donnees={(repartition.data?.categories ?? [])
                    .filter((l) => l.delai_moyen_heures !== null)
                    .map((l) => ({ cle: l.cle, valeur: Math.round(l.delai_moyen_heures ?? 0) }))}
                />
              ) : (
                <p className="text-sm text-muted-foreground">
                  Pas encore de données : il faut une date de publication et une date de vente.
                </p>
              )}
            </section>
          </div>
        </div>
      )}
    </>
  );
}
