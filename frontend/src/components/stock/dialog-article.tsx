"use client";

import { useMutation } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
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
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { formatEuros, saisieVersDecimal } from "@/lib/format";
import { useBatches, useComptes, useInvaliderStock } from "@/lib/queries";
import { ETATS, ORDRE_STATUTS, STATUTS } from "@/lib/statuts";
import type { Article } from "@/lib/types";

const VIDE = {
  nom: "",
  marque: "",
  categorie: "",
  taille: "",
  couleur: "",
  etat: "",
  prix_achat_brut: "",
  remise: "",
  prix_vente_cible: "",
  batch_id: "",
  compte_id: "",
  source: "",
  statut: "recu_a_publier",
  notes: "",
};

export function DialogArticle({ ouvert, setOuvert }: { ouvert: boolean; setOuvert: (v: boolean) => void }) {
  const router = useRouter();
  const invalider = useInvaliderStock();
  const { data: batches } = useBatches();
  const { data: comptes } = useComptes();
  const [f, setF] = useState(VIDE);
  const maj = (cle: keyof typeof VIDE) => (v: string) => setF((p) => ({ ...p, [cle]: v }));

  const brut = saisieVersDecimal(f.prix_achat_brut);
  const remise = saisieVersDecimal(f.remise) ?? "0";
  const net = brut !== null ? Number(brut) - Number(remise) : null;
  const erreurs = {
    nom: !f.nom.trim() ? "Le nom est obligatoire." : null,
    prix: f.prix_achat_brut && brut === null ? "Montant invalide." : null,
    remise: f.remise && saisieVersDecimal(f.remise) === null ? "Montant invalide." : null,
    vente: f.prix_vente_cible && saisieVersDecimal(f.prix_vente_cible) === null ? "Montant invalide." : null,
  };
  const valide = !Object.values(erreurs).some(Boolean);

  const creation = useMutation({
    mutationFn: () =>
      api<Article>("/articles", {
        body: {
          nom: f.nom.trim(),
          marque: f.marque || null,
          categorie: f.categorie || null,
          taille: f.taille || null,
          couleur: f.couleur || null,
          etat: f.etat || null,
          prix_achat_brut: brut,
          remise,
          prix_vente_cible: saisieVersDecimal(f.prix_vente_cible),
          batch_id: f.batch_id ? Number(f.batch_id) : null,
          compte_id: f.compte_id ? Number(f.compte_id) : comptes?.length === 1 ? comptes[0].id : null,
          source: f.source || null,
          statut: f.statut,
          notes: f.notes || null,
        },
      }),
    onSuccess: (a) => {
      invalider();
      toast.success("Article ajouté", {
        action: { label: "Ouvrir", onClick: () => router.push(`/stock/${a.id}`) },
      });
      setF(VIDE);
      setOuvert(false);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Dialog open={ouvert} onOpenChange={setOuvert}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Ajouter un article</DialogTitle>
          <DialogDescription>Le prix net est calculé automatiquement : brut − remise.</DialogDescription>
        </DialogHeader>
        <form
          id="form-article"
          className="grid grid-cols-2 gap-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (valide) creation.mutate();
          }}
        >
          <Champ id="nom" libelle="Nom de l'article" erreur={erreurs.nom} className="col-span-2">
            <Input
              id="nom"
              value={f.nom}
              onChange={(e) => maj("nom")(e.target.value)}
              placeholder="Hoodie Carhartt WIP - noir"
              autoFocus
            />
          </Champ>
          <Champ id="marque" libelle="Marque">
            <Input id="marque" value={f.marque} onChange={(e) => maj("marque")(e.target.value)} />
          </Champ>
          <Champ id="categorie" libelle="Catégorie">
            <Input id="categorie" value={f.categorie} onChange={(e) => maj("categorie")(e.target.value)} />
          </Champ>
          <Champ id="taille" libelle="Taille">
            <Input id="taille" value={f.taille} onChange={(e) => maj("taille")(e.target.value)} />
          </Champ>
          <Champ id="couleur" libelle="Couleur">
            <Input id="couleur" value={f.couleur} onChange={(e) => maj("couleur")(e.target.value)} />
          </Champ>
          <Champ id="prix-brut" libelle="Prix d'achat brut (€)" erreur={erreurs.prix}>
            <Input
              id="prix-brut"
              inputMode="decimal"
              value={f.prix_achat_brut}
              onChange={(e) => maj("prix_achat_brut")(e.target.value)}
            />
          </Champ>
          <Champ id="remise" libelle="Remise (€)" erreur={erreurs.remise}>
            <Input
              id="remise"
              inputMode="decimal"
              value={f.remise}
              onChange={(e) => maj("remise")(e.target.value)}
              placeholder="0"
            />
          </Champ>
          <Champ id="prix-vente" libelle="Prix de vente cible (€)" erreur={erreurs.vente}>
            <Input
              id="prix-vente"
              inputMode="decimal"
              value={f.prix_vente_cible}
              onChange={(e) => maj("prix_vente_cible")(e.target.value)}
            />
          </Champ>
          <div className="flex flex-col justify-end rounded-lg bg-muted/50 px-3 py-2 text-sm">
            <span className="text-xs text-muted-foreground">Prix d&apos;achat net</span>
            <span className="font-medium tabular-nums">
              {net !== null && !Number.isNaN(net) ? formatEuros(net) : "—"}
            </span>
          </div>
          <Champ id="etat" libelle="État">
            <Select value={f.etat} onValueChange={maj("etat")}>
              <SelectTrigger id="etat" className="w-full">
                <SelectValue placeholder="Non renseigné" />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(ETATS).map(([v, l]) => (
                  <SelectItem key={v} value={v}>
                    {l}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Champ>
          <Champ id="statut" libelle="Statut">
            <Select value={f.statut} onValueChange={maj("statut")}>
              <SelectTrigger id="statut" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {ORDRE_STATUTS.map((s) => (
                  <SelectItem key={s} value={s}>
                    {STATUTS[s].libelle}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Champ>
          <Champ id="batch" libelle="Batch">
            <Select value={f.batch_id} onValueChange={maj("batch_id")}>
              <SelectTrigger id="batch" className="w-full">
                <SelectValue placeholder="Aucun" />
              </SelectTrigger>
              <SelectContent>
                {batches?.map((b) => (
                  <SelectItem key={b.id} value={String(b.id)}>
                    {b.nom}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Champ>
          {(comptes?.length ?? 0) > 1 && (
            <Champ id="compte" libelle="Compte Vinted">
              <Select value={f.compte_id} onValueChange={maj("compte_id")}>
                <SelectTrigger id="compte" className="w-full">
                  <SelectValue placeholder="Pas encore attribué" />
                </SelectTrigger>
                <SelectContent>
                  {comptes?.map((c) => (
                    <SelectItem key={c.id} value={String(c.id)}>
                      {c.nom}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Champ>
          )}
          <Champ id="source" libelle="Source">
            <Input id="source" value={f.source} onChange={(e) => maj("source")(e.target.value)} placeholder="Hacoo" />
          </Champ>
          <Champ id="notes" libelle="Notes" className="col-span-2">
            <Textarea id="notes" rows={2} value={f.notes} onChange={(e) => maj("notes")(e.target.value)} />
          </Champ>
        </form>
        <DialogFooter>
          <Button variant="outline" onClick={() => setOuvert(false)}>
            Annuler
          </Button>
          <Button type="submit" form="form-article" disabled={!valide || creation.isPending}>
            {creation.isPending && <Loader2 className="animate-spin" />}
            Ajouter
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export function Champ({
  id,
  libelle,
  erreur,
  className,
  children,
}: {
  id: string;
  libelle: string;
  erreur?: string | null;
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <div className={`space-y-1.5 ${className ?? ""}`}>
      <Label htmlFor={id}>{libelle}</Label>
      {children}
      {erreur && (
        <p className="text-xs text-destructive" role="alert">
          {erreur}
        </p>
      )}
    </div>
  );
}
