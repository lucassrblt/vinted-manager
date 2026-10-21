"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronsUpDown } from "lucide-react";
import { useState } from "react";

import { StatutBadge } from "@/components/commun";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandGroup, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useDebounce } from "@/hooks/use-debounce";
import { api } from "@/lib/api";
import type { Article, Page, Statut } from "@/lib/types";

/** Recherche d'un article par son nom, pour rattacher un mail ou confirmer une vente à la main. */
export function SelecteurArticle({
  libelle = "Choisir un article",
  statuts,
  onChoix,
  desactive,
}: {
  libelle?: string;
  statuts?: Statut[];
  onChoix: (article: Article) => void;
  desactive?: boolean;
}) {
  const [ouvert, setOuvert] = useState(false);
  const [q, setQ] = useState("");
  const recherche = useDebounce(q, 200);
  const { data } = useQuery({
    queryKey: ["articles", "selecteur", recherche, statuts],
    queryFn: () => api<Page<Article>>("/articles", { params: { q: recherche, statut: statuts, taille_page: 15 } }),
    enabled: ouvert,
  });
  return (
    <Popover open={ouvert} onOpenChange={setOuvert}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" disabled={desactive} className="justify-between">
          {libelle}
          <ChevronsUpDown className="opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="start">
        <Command shouldFilter={false}>
          <CommandInput placeholder="Nom, marque, couleur…" value={q} onValueChange={setQ} />
          <CommandList>
            <CommandEmpty>Aucun article.</CommandEmpty>
            <CommandGroup>
              {data?.items.map((a) => (
                <CommandItem
                  key={a.id}
                  value={String(a.id)}
                  onSelect={() => {
                    setOuvert(false);
                    onChoix(a);
                  }}
                >
                  <span className="min-w-0 flex-1 truncate">
                    {a.nom}
                    {a.taille && <span className="text-muted-foreground"> · {a.taille}</span>}
                  </span>
                  <StatutBadge statut={a.statut} />
                </CommandItem>
              ))}
            </CommandGroup>
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
