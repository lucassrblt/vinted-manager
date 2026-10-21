import type { LucideIcon } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { INDICATEURS, STATUTS } from "@/lib/statuts";
import type { Statut } from "@/lib/types";
import { cn } from "@/lib/utils";

export function StatutBadge({ statut, className }: { statut: Statut; className?: string }) {
  const s = STATUTS[statut];
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center gap-1.5 rounded-full px-2 text-xs font-medium whitespace-nowrap",
        s.classe,
        className,
      )}
    >
      <span aria-hidden className={cn("size-1.5 rounded-full", s.point)} />
      {s.libelle}
    </span>
  );
}

export function IndicateurBadge({ indicateur }: { indicateur: string | null }) {
  if (!indicateur) return null;
  return (
    <span
      className={cn(
        "inline-flex h-5 items-center rounded-full px-2 text-[11px] font-medium whitespace-nowrap",
        INDICATEURS[indicateur],
      )}
    >
      {indicateur}
    </span>
  );
}

export function EnTetePage({
  titre,
  description,
  actions,
}: {
  titre: string;
  description?: React.ReactNode;
  actions?: React.ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight">{titre}</h1>
        {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function EtatVide({
  icone: Icone,
  titre,
  texte,
  action,
}: {
  icone: LucideIcon;
  titre: string;
  texte?: string;
  action?: { libelle: string; href?: string; onClick?: () => void };
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed px-6 py-14 text-center">
      <div className="relative mb-4">
        <div aria-hidden className="absolute inset-0 -m-3 rounded-full bg-brand-soft blur-md" />
        <div className="relative flex size-12 items-center justify-center rounded-xl border bg-card shadow-sm">
          <Icone className="size-5 text-brand" />
        </div>
      </div>
      <h3 className="font-medium">{titre}</h3>
      {texte && <p className="mt-1 max-w-sm text-sm text-muted-foreground">{texte}</p>}
      {action &&
        (action.href ? (
          <Button asChild className="mt-5" size="lg">
            <Link href={action.href}>{action.libelle}</Link>
          </Button>
        ) : (
          <Button className="mt-5" size="lg" onClick={action.onClick}>
            {action.libelle}
          </Button>
        ))}
    </div>
  );
}

export function CarteKpi({
  libelle,
  valeur,
  detail,
  icone: Icone,
  href,
  ton,
}: {
  libelle: string;
  valeur: React.ReactNode;
  detail?: React.ReactNode;
  icone?: LucideIcon;
  href?: string;
  ton?: "alerte" | "brand";
}) {
  const contenu = (
    <>
      <div className="flex items-center justify-between gap-2">
        <span className="text-[13px] text-muted-foreground">{libelle}</span>
        {Icone && (
          <Icone
            className={cn(
              "size-4 text-muted-foreground/70",
              ton === "alerte" && "text-red-500",
              ton === "brand" && "text-brand",
            )}
          />
        )}
      </div>
      <div className="mt-2 text-2xl font-semibold tracking-tight tabular-nums">{valeur}</div>
      {detail && <div className="mt-1 text-xs text-muted-foreground">{detail}</div>}
    </>
  );
  const classes = cn(
    "block rounded-xl border bg-card p-4 shadow-[0_1px_2px_rgba(0,0,0,0.03)]",
    ton === "alerte" && "border-red-200 dark:border-red-900/60",
    href &&
      "transition-colors hover:border-foreground/20 hover:bg-accent/40 focus-visible:ring-3 focus-visible:ring-ring/50 outline-none",
  );
  return href ? (
    <Link href={href} className={classes}>
      {contenu}
    </Link>
  ) : (
    <div className={classes}>{contenu}</div>
  );
}

export function GrilleSquelette({ n = 4, hauteur = "h-24" }: { n?: number; hauteur?: string }) {
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {Array.from({ length: n }, (_, i) => (
        <Skeleton key={i} className={cn("rounded-xl", hauteur)} />
      ))}
    </div>
  );
}

export function LignesSquelette({ n = 8 }: { n?: number }) {
  return (
    <div className="space-y-2">
      {Array.from({ length: n }, (_, i) => (
        <Skeleton key={i} className="h-10 rounded-lg" />
      ))}
    </div>
  );
}

export function MessageErreur({ erreur, reessayer }: { erreur: unknown; reessayer?: () => void }) {
  return (
    <div role="alert" className="rounded-xl border border-destructive/30 bg-destructive/5 p-4 text-sm">
      <p className="font-medium text-destructive">Le chargement a échoué</p>
      <p className="mt-1 text-muted-foreground">{erreur instanceof Error ? erreur.message : "Erreur inconnue."}</p>
      {reessayer && (
        <Button variant="outline" size="sm" className="mt-3" onClick={reessayer}>
          Réessayer
        </Button>
      )}
    </div>
  );
}
