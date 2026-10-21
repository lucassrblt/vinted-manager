"use client";

import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Clock,
  Inbox,
  MessageCircle,
  PackageCheck,
  PackageOpen,
  Receipt,
  Target,
  Truck,
} from "lucide-react";
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
          {d.litiges > 0 && (
            <Link
              href="/stock?statut=litige"
              className="flex items-center gap-3 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 hover:bg-red-100 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300"
            >
              <AlertTriangle className="size-5 shrink-0" />
              <span className="flex-1">
                <strong>
                  {d.litiges} litige{d.litiges > 1 ? "s" : ""} en cours
                </strong>{" "}
                · tes preuves d&apos;achat sont prêtes à télécharger depuis la fiche de l&apos;article.
              </span>
            </Link>
          )}

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
              libelle="Colis à envoyer"
              valeur={d.envois.a_preparer}
              icone={PackageCheck}
              href="/envois"
              ton={d.envois.en_retard ? "alerte" : d.envois.aujourdhui ? "brand" : undefined}
              detail={
                d.envois.en_retard
                  ? `${d.envois.en_retard} en retard · ${d.envois.aujourdhui} aujourd'hui`
                  : d.envois.aujourdhui
                    ? `${d.envois.aujourdhui} à déposer aujourd'hui`
                    : "rien d'urgent"
              }
            />
            <CarteKpi
              libelle="Ventes à confirmer"
              valeur={d.ventes_a_confirmer}
              icone={Receipt}
              href="/ventes"
              detail={d.ventes_a_confirmer ? "un clic pour choisir l'article" : "tout est rapproché"}
            />
            <CarteKpi
              libelle="Messages et offres"
              valeur={d.messages_a_traiter}
              icone={MessageCircle}
              href="/messages"
              detail={d.messages_a_traiter ? "réponse suggérée prête en un clic" : "rien à répondre"}
            />
            <CarteKpi
              libelle="Mails non classés"
              valeur={d.mails_non_classes}
              icone={Inbox}
              href="/mails"
              detail={d.mails_non_classes ? "à classer ou à transformer en règle" : "tout est reconnu"}
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
                Avec une suggestion de nouveau prix (−10 %, jamais sous le coefficient minimal).
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
                      <span className="text-sm tabular-nums">
                        {a.prix_suggere ? (
                          <>
                            <span className="text-muted-foreground line-through">{formatEuros(a.prix_vente)}</span>{" "}
                            <span className="font-medium text-brand">{formatEuros(a.prix_suggere)}</span>
                          </>
                        ) : (
                          formatEuros(a.prix_vente)
                        )}
                      </span>
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
