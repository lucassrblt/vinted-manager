"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, LogOut, Menu, Monitor, Moon, Search, Sun } from "lucide-react";
import Link from "next/link";
import { useTheme } from "next-themes";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { api } from "@/lib/api";

import { ListeNavigation, Logo } from "./sidebar";

function BasculeTheme() {
  const { setTheme } = useTheme();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" aria-label="Changer de thème">
          <Sun className="dark:hidden" />
          <Moon className="hidden dark:block" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem onClick={() => setTheme("light")}>
          <Sun /> Clair
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("dark")}>
          <Moon /> Sombre
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => setTheme("system")}>
          <Monitor /> Système
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function AlerteLitiges() {
  const { data } = useQuery({
    queryKey: ["alertes"],
    queryFn: () => api<{ litiges: { id: number; nom: string }[] }>("/alertes"),
    refetchInterval: 60_000,
  });
  const litiges = data?.litiges ?? [];
  if (litiges.length === 0) return null;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className="gap-1.5 bg-red-50 text-red-700 hover:bg-red-100 hover:text-red-800 dark:bg-red-950/50 dark:text-red-300"
        >
          <AlertTriangle />
          <span>
            {litiges.length} litige{litiges.length > 1 ? "s" : ""}
          </span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuLabel>Litiges ouverts</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {litiges.map((l) => (
          <DropdownMenuItem key={l.id} asChild>
            <Link href={`/stock/${l.id}`} className="truncate">
              {l.nom}
            </Link>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function Header({ ouvrirRecherche }: { ouvrirRecherche: () => void }) {
  const [menuMobile, setMenuMobile] = useState(false);
  const { data: moi } = useQuery({ queryKey: ["moi"], queryFn: () => api<{ email: string }>("/auth/me") });

  async function deconnexion() {
    await api("/auth/logout", { method: "POST" }).catch(() => undefined);
    window.location.href = "/login";
  }

  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-2 border-b bg-background/80 px-4 backdrop-blur supports-[backdrop-filter]:bg-background/70 md:px-6">
      <Button
        variant="ghost"
        size="icon"
        className="md:hidden"
        onClick={() => setMenuMobile(true)}
        aria-label="Ouvrir le menu"
      >
        <Menu />
      </Button>
      <div className="md:hidden">
        <Logo />
      </div>

      <button
        type="button"
        onClick={ouvrirRecherche}
        className="ml-auto flex h-8 items-center gap-2 rounded-lg border bg-muted/40 px-2.5 text-sm text-muted-foreground transition-colors outline-none hover:bg-muted focus-visible:ring-3 focus-visible:ring-ring/50 md:ml-0 md:w-72"
        aria-label="Rechercher (Cmd+K)"
      >
        <Search className="size-4" />
        <span className="hidden md:inline">Rechercher…</span>
        <kbd className="ml-auto hidden rounded border bg-background px-1.5 font-mono text-[10px] md:inline">⌘K</kbd>
      </button>

      <div className="flex items-center gap-1 md:ml-auto">
        <AlerteLitiges />
        <BasculeTheme />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" size="icon" aria-label="Compte">
              <span className="flex size-6 items-center justify-center rounded-full bg-brand-soft text-xs font-semibold text-brand uppercase">
                {moi?.email?.[0] ?? "·"}
              </span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuLabel className="font-normal text-muted-foreground">{moi?.email}</DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={deconnexion}>
              <LogOut /> Se déconnecter
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      <Sheet open={menuMobile} onOpenChange={setMenuMobile}>
        <SheetContent side="left" className="w-72 p-0">
          <SheetHeader className="h-14 justify-center border-b px-4">
            <SheetTitle asChild>
              <div>
                <Logo />
              </div>
            </SheetTitle>
          </SheetHeader>
          <div className="px-3 py-3">
            <ListeNavigation onNavigate={() => setMenuMobile(false)} />
          </div>
        </SheetContent>
      </Sheet>
    </header>
  );
}
