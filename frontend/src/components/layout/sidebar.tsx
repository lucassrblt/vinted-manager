"use client";

import { PanelLeftClose, PanelLeftOpen, Shirt } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { cn } from "@/lib/utils";

import { estActif, NAVIGATION } from "./navigation";

export function ListeNavigation({ replie = false, onNavigate }: { replie?: boolean; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Navigation principale" className="flex flex-col gap-5">
      {NAVIGATION.map((section, i) => (
        <div key={i} className="flex flex-col gap-0.5">
          {section.groupe && !replie && (
            <span className="px-2.5 pb-1 text-[11px] font-medium tracking-wide text-muted-foreground/80 uppercase">
              {section.groupe}
            </span>
          )}
          {section.liens.map(({ href, libelle, icone: Icone }) => {
            const actif = estActif(pathname, href);
            const lien = (
              <Link
                key={href}
                href={href}
                onClick={onNavigate}
                aria-current={actif ? "page" : undefined}
                className={cn(
                  "group flex h-8 items-center gap-2.5 rounded-md px-2.5 text-sm text-muted-foreground transition-colors outline-none",
                  "hover:bg-sidebar-accent hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/60",
                  actif && "bg-sidebar-accent font-medium text-foreground",
                  replie && "justify-center px-0",
                )}
              >
                <Icone className={cn("size-4 shrink-0", actif && "text-brand")} />
                {!replie && <span className="truncate">{libelle}</span>}
              </Link>
            );
            return replie ? (
              <Tooltip key={href}>
                <TooltipTrigger asChild>{lien}</TooltipTrigger>
                <TooltipContent side="right">{libelle}</TooltipContent>
              </Tooltip>
            ) : (
              lien
            );
          })}
        </div>
      ))}
    </nav>
  );
}

export function Logo({ replie = false }: { replie?: boolean }) {
  return (
    <Link
      href="/"
      className="flex items-center gap-2 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-ring/60"
    >
      <span className="flex size-7 items-center justify-center rounded-lg bg-brand text-brand-foreground">
        <Shirt className="size-4" />
      </span>
      {!replie && <span className="text-[15px] font-semibold tracking-tight">Revente</span>}
    </Link>
  );
}

export function Sidebar({ replie, basculer }: { replie: boolean; basculer: () => void }) {
  return (
    <aside
      className={cn(
        "sticky top-0 hidden h-dvh shrink-0 flex-col border-r bg-sidebar transition-[width] duration-200 md:flex",
        replie ? "w-[60px]" : "w-60",
      )}
    >
      <div className={cn("flex h-14 items-center px-4", replie && "justify-center px-0")}>
        <Logo replie={replie} />
      </div>
      <div className="flex-1 overflow-y-auto px-3 py-2">
        <ListeNavigation replie={replie} />
      </div>
      <div className={cn("border-t p-3", replie && "flex justify-center")}>
        <Button
          variant="ghost"
          size={replie ? "icon" : "sm"}
          onClick={basculer}
          className="text-muted-foreground"
          aria-label={replie ? "Déplier la barre latérale" : "Replier la barre latérale"}
        >
          {replie ? <PanelLeftOpen /> : <PanelLeftClose />}
          {!replie && "Replier"}
        </Button>
      </div>
    </aside>
  );
}
