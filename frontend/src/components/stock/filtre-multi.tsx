"use client";

import { Check, ChevronDown, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export interface OptionFiltre<T extends string | number> {
  valeur: T;
  libelle: string;
}

export function FiltreMulti<T extends string | number>({
  titre,
  options,
  selection,
  onChange,
}: {
  titre: string;
  options: OptionFiltre<T>[];
  selection: T[];
  onChange: (v: T[]) => void;
}) {
  const choisis = new Set(selection);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" className={cn("border-dashed", choisis.size > 0 && "border-solid")}>
          {titre}
          {choisis.size > 0 && (
            <span className="rounded bg-brand-soft px-1.5 text-[11px] font-semibold text-brand tabular-nums">
              {choisis.size}
            </span>
          )}
          <ChevronDown className="opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-56 p-0" align="start">
        <Command>
          {options.length > 7 && <CommandInput placeholder={titre} />}
          <CommandList>
            <CommandEmpty>Aucune valeur.</CommandEmpty>
            <CommandGroup>
              {options.map((o) => {
                const actif = choisis.has(o.valeur);
                return (
                  <CommandItem
                    key={String(o.valeur)}
                    value={o.libelle}
                    onSelect={() =>
                      onChange(actif ? selection.filter((v) => v !== o.valeur) : [...selection, o.valeur])
                    }
                  >
                    <span
                      className={cn(
                        "flex size-4 items-center justify-center rounded border",
                        actif && "border-brand bg-brand text-brand-foreground",
                      )}
                    >
                      {actif && <Check className="size-3" />}
                    </span>
                    <span className="truncate">{o.libelle}</span>
                  </CommandItem>
                );
              })}
            </CommandGroup>
            {choisis.size > 0 && (
              <>
                <CommandSeparator />
                <CommandGroup>
                  <CommandItem onSelect={() => onChange([])} className="justify-center text-muted-foreground">
                    <X /> Effacer
                  </CommandItem>
                </CommandGroup>
              </>
            )}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
