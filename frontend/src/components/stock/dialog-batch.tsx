"use client";

import { useMutation } from "@tanstack/react-query";
import { Loader2, Plus, Trash2 } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import { aujourdhuiParis, formatEuros, saisieVersDecimal } from "@/lib/format";
import { useInvaliderStock } from "@/lib/queries";
import { STATUTS } from "@/lib/statuts";
import type { BatchStats } from "@/lib/types";

import { Champ } from "./dialog-article";

interface Ligne {
  nom: string;
  taille: string;
  prix: string;
  vente: string;
  quantite: string;
}

const LIGNE_VIDE: Ligne = { nom: "", taille: "", prix: "", vente: "", quantite: "1" };

/** Même règle que le backend (plus fort reste) : aperçu en centimes de la remise par unité. */
export function repartirRemise(bruts: number[], remise: number): number[] {
  const total = bruts.reduce((a, b) => a + b, 0);
  if (!bruts.length || remise <= 0 || total <= 0 || remise > total) return bruts.map(() => 0);
  const centimes = Math.round(remise * 100);
  const exactes = bruts.map((b) => (centimes * b) / total);
  const base = exactes.map(Math.floor);
  let reste = centimes - base.reduce((a, b) => a + b, 0);
  const ordre = exactes.map((e, i) => [e - base[i], bruts[i], i] as const).sort((a, b) => b[0] - a[0] || b[1] - a[1]);
  for (const [, , i] of ordre) {
    if (reste-- <= 0) break;
    base[i] += 1;
  }
  return base.map((c) => c / 100);
}

export function DialogBatch({ ouvert, setOuvert }: { ouvert: boolean; setOuvert: (v: boolean) => void }) {
  const router = useRouter();
  const invalider = useInvaliderStock();
  const [nom, setNom] = useState("");
  const [fournisseur, setFournisseur] = useState("");
  const [date, setDate] = useState(aujourdhuiParis());
  const [remise, setRemise] = useState("");
  const [statut, setStatut] = useState("commande");
  const [lignes, setLignes] = useState<Ligne[]>([{ ...LIGNE_VIDE }]);

  const majLigne = (i: number, cle: keyof Ligne, v: string) =>
    setLignes((ls) => ls.map((l, j) => (j === i ? { ...l, [cle]: v } : l)));

  const lignesValides = lignes.filter((l) => l.nom.trim() && saisieVersDecimal(l.prix) !== null);
  const unites = lignesValides.flatMap((l) =>
    Array.from({ length: Math.max(1, Number(l.quantite) || 1) }, () => Number(saisieVersDecimal(l.prix))),
  );
  const totalBrut = unites.reduce((a, b) => a + b, 0);
  const remiseNum = Number(saisieVersDecimal(remise) ?? 0);
  const remises = repartirRemise(unites, remiseNum);
  // Remise allouée à la première unité de chaque ligne, pour l'aperçu
  let curseur = 0;
  const remiseParLigne = lignesValides.map((l) => {
    const r = remises[curseur] ?? 0;
    curseur += Math.max(1, Number(l.quantite) || 1);
    return r;
  });

  const erreur = !nom.trim()
    ? "Donne un nom au batch."
    : remiseNum > totalBrut && totalBrut > 0
      ? "La remise dépasse le total brut."
      : remise && saisieVersDecimal(remise) === null
        ? "Remise invalide."
        : null;

  const creation = useMutation({
    mutationFn: () =>
      api<BatchStats>("/batches", {
        body: {
          nom: nom.trim(),
          fournisseur: fournisseur || null,
          date_commande: date || null,
          remise_globale: saisieVersDecimal(remise) ?? "0",
          statut_articles: statut,
          articles: lignesValides.map((l) => ({
            nom: l.nom.trim(),
            taille: l.taille || null,
            prix_achat_brut: saisieVersDecimal(l.prix),
            prix_vente_cible: saisieVersDecimal(l.vente),
            quantite: Math.min(50, Math.max(1, Number(l.quantite) || 1)),
          })),
        },
      }),
    onSuccess: (b) => {
      invalider();
      toast.success(`Batch « ${b.nom} » créé avec ${b.nb_articles} article(s)`);
      setOuvert(false);
      setNom("");
      setRemise("");
      setLignes([{ ...LIGNE_VIDE }]);
      router.push(`/batches/${b.id}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Dialog open={ouvert} onOpenChange={setOuvert}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Ajouter un batch</DialogTitle>
          <DialogDescription>
            Saisis plusieurs articles d&apos;un coup : la remise globale est répartie au prorata du prix brut.
          </DialogDescription>
        </DialogHeader>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Champ id="b-nom" libelle="Nom" className="col-span-2 sm:col-span-1">
            <Input id="b-nom" value={nom} onChange={(e) => setNom(e.target.value)} placeholder="Batch 5" autoFocus />
          </Champ>
          <Champ id="b-fournisseur" libelle="Fournisseur">
            <Input
              id="b-fournisseur"
              value={fournisseur}
              onChange={(e) => setFournisseur(e.target.value)}
              placeholder="Hacoo"
            />
          </Champ>
          <Champ id="b-date" libelle="Date de commande">
            <Input id="b-date" type="date" value={date} onChange={(e) => setDate(e.target.value)} />
          </Champ>
          <Champ id="b-remise" libelle="Remise globale (€)">
            <Input
              id="b-remise"
              inputMode="decimal"
              value={remise}
              onChange={(e) => setRemise(e.target.value)}
              placeholder="0"
            />
          </Champ>
          <Champ id="b-statut" libelle="Statut des articles" className="col-span-2 sm:col-span-1">
            <Select value={statut} onValueChange={setStatut}>
              <SelectTrigger id="b-statut" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {(["commande", "recu_a_publier"] as const).map((s) => (
                  <SelectItem key={s} value={s}>
                    {STATUTS[s].libelle}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Champ>
        </div>

        <div className="rounded-lg border">
          <div className="hidden grid-cols-[1fr_70px_90px_90px_56px_80px_32px] gap-2 border-b bg-muted/40 px-3 py-2 text-xs font-medium text-muted-foreground sm:grid">
            <span>Article</span>
            <span>Taille</span>
            <span className="text-right">Prix brut</span>
            <span className="text-right">Vente cible</span>
            <span className="text-right">Qté</span>
            <span className="text-right">Net / unité</span>
            <span />
          </div>
          <div className="divide-y">
            {lignes.map((l, i) => {
              const idx = lignesValides.indexOf(l);
              const brut = saisieVersDecimal(l.prix);
              const netUnite = brut !== null && idx >= 0 ? Number(brut) - remiseParLigne[idx] : null;
              return (
                <div
                  key={i}
                  className="grid grid-cols-6 gap-2 px-3 py-2 sm:grid-cols-[1fr_70px_90px_90px_56px_80px_32px]"
                >
                  <Input
                    aria-label={`Nom de l'article ${i + 1}`}
                    className="col-span-6 h-8 sm:col-span-1"
                    value={l.nom}
                    onChange={(e) => majLigne(i, "nom", e.target.value)}
                    placeholder="Pull demi-zip Ralph Lauren - noir"
                  />
                  <Input
                    aria-label="Taille"
                    className="col-span-1 h-8"
                    value={l.taille}
                    onChange={(e) => majLigne(i, "taille", e.target.value)}
                    placeholder="M"
                  />
                  <Input
                    aria-label="Prix brut"
                    inputMode="decimal"
                    className="col-span-2 h-8 text-right sm:col-span-1"
                    value={l.prix}
                    onChange={(e) => majLigne(i, "prix", e.target.value)}
                    placeholder="0,00"
                  />
                  <Input
                    aria-label="Prix de vente cible"
                    inputMode="decimal"
                    className="col-span-2 h-8 text-right sm:col-span-1"
                    value={l.vente}
                    onChange={(e) => majLigne(i, "vente", e.target.value)}
                    placeholder="—"
                  />
                  <Input
                    aria-label="Quantité"
                    inputMode="numeric"
                    className="col-span-1 h-8 text-right"
                    value={l.quantite}
                    onChange={(e) => majLigne(i, "quantite", e.target.value.replace(/\D/g, ""))}
                  />
                  <span className="col-span-5 flex items-center justify-end text-sm text-muted-foreground tabular-nums sm:col-span-1">
                    {netUnite !== null ? formatEuros(netUnite) : "—"}
                  </span>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    aria-label="Retirer la ligne"
                    disabled={lignes.length === 1}
                    onClick={() => setLignes((ls) => ls.filter((_, j) => j !== i))}
                  >
                    <Trash2 />
                  </Button>
                </div>
              );
            })}
          </div>
          <div className="flex items-center justify-between border-t px-3 py-2">
            <Button variant="ghost" size="sm" onClick={() => setLignes((ls) => [...ls, { ...LIGNE_VIDE }])}>
              <Plus /> Ajouter une ligne
            </Button>
            <span className="text-sm text-muted-foreground tabular-nums">
              {unites.length} unité(s) · brut {formatEuros(totalBrut)} · payé{" "}
              {formatEuros(Math.max(0, totalBrut - remiseNum))}
            </span>
          </div>
        </div>

        {erreur && nom && <p className="text-sm text-destructive">{erreur}</p>}

        <DialogFooter>
          <Button variant="outline" onClick={() => setOuvert(false)}>
            Annuler
          </Button>
          <Button onClick={() => creation.mutate()} disabled={!!erreur || creation.isPending}>
            {creation.isPending && <Loader2 className="animate-spin" />}
            Créer le batch
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
