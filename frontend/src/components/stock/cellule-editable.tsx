"use client";

import { useEffect, useRef, useState } from "react";

import { saisieVersDecimal } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * Cellule éditable en place : clic (ou Entrée) pour éditer, Entrée pour valider, Échap pour annuler.
 * `type="montant"` accepte la saisie française (« 12,50 ») et envoie « 12.50 ».
 */
export function CelluleEditable({
  valeur,
  affichage,
  onSave,
  type = "texte",
  libelle,
  className,
}: {
  valeur: string | null;
  affichage?: React.ReactNode;
  onSave: (v: string | null) => void;
  type?: "texte" | "montant";
  libelle: string;
  className?: string;
}) {
  const [edition, setEdition] = useState(false);
  const [brouillon, setBrouillon] = useState("");
  const [invalide, setInvalide] = useState(false);
  const ref = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (edition) ref.current?.select();
  }, [edition]);

  function demarrer() {
    setBrouillon(type === "montant" && valeur ? valeur.replace(".", ",") : (valeur ?? ""));
    setInvalide(false);
    setEdition(true);
  }

  function valider() {
    const texte = brouillon.trim();
    let nouvelle: string | null = texte === "" ? null : texte;
    if (type === "montant" && texte !== "") {
      nouvelle = saisieVersDecimal(texte);
      if (nouvelle === null || Number(nouvelle) < 0) {
        setInvalide(true);
        return;
      }
    }
    setEdition(false);
    const avant = type === "montant" && valeur !== null ? String(Number(valeur)) : valeur;
    const apres = type === "montant" && nouvelle !== null ? String(Number(nouvelle)) : nouvelle;
    if (apres !== avant) onSave(nouvelle);
  }

  if (edition) {
    return (
      <input
        ref={ref}
        aria-label={libelle}
        aria-invalid={invalide}
        inputMode={type === "montant" ? "decimal" : undefined}
        value={brouillon}
        onChange={(e) => setBrouillon(e.target.value)}
        onBlur={valider}
        onKeyDown={(e) => {
          if (e.key === "Enter") valider();
          if (e.key === "Escape") setEdition(false);
        }}
        className={cn(
          "h-7 w-full min-w-16 rounded-md border bg-background px-1.5 text-sm outline-none focus:ring-2 focus:ring-ring/50",
          type === "montant" && "text-right tabular-nums",
          invalide && "border-destructive ring-2 ring-destructive/20",
        )}
      />
    );
  }
  return (
    <button
      type="button"
      onClick={demarrer}
      aria-label={`Modifier ${libelle}`}
      className={cn(
        "-mx-1.5 block h-7 w-[calc(100%+0.75rem)] truncate rounded-md px-1.5 text-left outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring/50",
        type === "montant" && "text-right tabular-nums",
        className,
      )}
    >
      {affichage ?? (valeur || <span className="text-muted-foreground/60">—</span>)}
    </button>
  );
}
