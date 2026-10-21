"use client";

import { useQuery } from "@tanstack/react-query";
import { Layers, Package } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { StatutBadge } from "@/components/commun";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { useDebounce } from "@/hooks/use-debounce";
import { api } from "@/lib/api";
import type { Statut } from "@/lib/types";

import { NAVIGATION } from "./navigation";

interface Resultats {
  articles: { id: number; nom: string; taille: string | null; statut: Statut }[];
  batches: { id: number; nom: string }[];
}

export function RechercheGlobale({ ouvert, setOuvert }: { ouvert: boolean; setOuvert: (v: boolean) => void }) {
  const router = useRouter();
  const [q, setQ] = useState("");
  const qDiffere = useDebounce(q, 200);

  useEffect(() => {
    function raccourci(e: KeyboardEvent) {
      if (e.key.toLowerCase() === "k" && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOuvert(!ouvert);
      }
    }
    window.addEventListener("keydown", raccourci);
    return () => window.removeEventListener("keydown", raccourci);
  }, [ouvert, setOuvert]);

  const { data } = useQuery({
    queryKey: ["recherche", qDiffere],
    queryFn: () => api<Resultats>("/search", { params: { q: qDiffere } }),
    enabled: qDiffere.trim().length >= 2,
  });

  function aller(href: string) {
    setOuvert(false);
    setQ("");
    router.push(href);
  }

  const pages = NAVIGATION.flatMap((s) => s.liens);

  return (
    <CommandDialog
      open={ouvert}
      onOpenChange={setOuvert}
      title="Recherche"
      description="Rechercher un article, un batch ou une page"
    >
      <Command shouldFilter={false}>
        <CommandInput placeholder="Article, marque, batch, page…" value={q} onValueChange={setQ} />
        <CommandList>
          <CommandEmpty>Aucun résultat.</CommandEmpty>
          {data && data.articles.length > 0 && (
            <CommandGroup heading="Articles">
              {data.articles.map((a) => (
                <CommandItem key={`a${a.id}`} value={`article-${a.id}`} onSelect={() => aller(`/stock/${a.id}`)}>
                  <Package />
                  <span className="truncate">{a.nom}</span>
                  {a.taille && <span className="text-muted-foreground">{a.taille}</span>}
                  <StatutBadge statut={a.statut} className="ml-auto" />
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          {data && data.batches.length > 0 && (
            <CommandGroup heading="Batches">
              {data.batches.map((b) => (
                <CommandItem key={`b${b.id}`} value={`batch-${b.id}`} onSelect={() => aller(`/batches/${b.id}`)}>
                  <Layers />
                  {b.nom}
                </CommandItem>
              ))}
            </CommandGroup>
          )}
          <CommandSeparator />
          <CommandGroup heading="Pages">
            {pages
              .filter((p) => p.libelle.toLowerCase().includes(q.toLowerCase()))
              .map(({ href, libelle, icone: Icone }) => (
                <CommandItem key={href} value={`page-${href}`} onSelect={() => aller(href)}>
                  <Icone />
                  {libelle}
                </CommandItem>
              ))}
          </CommandGroup>
        </CommandList>
      </Command>
    </CommandDialog>
  );
}
