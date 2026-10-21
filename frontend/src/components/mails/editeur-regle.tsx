"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { FlaskConical, Loader2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Champ } from "@/components/stock/dialog-article";
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
import { Switch } from "@/components/ui/switch";
import { api } from "@/lib/api";
import { TYPES_EMAIL } from "@/lib/statuts";
import type { DonneesExtraites, Regle, TypeEmail } from "@/lib/types";

export type BrouillonRegle = Omit<Regle, "id" | "created_at"> & { id?: number };

const CHAMPS_EXTRACTION: { cle: keyof DonneesExtraites; libelle: string }[] = [
  { cle: "prix", libelle: "Prix de vente" },
  { cle: "montant_offre", libelle: "Montant de l'offre" },
  { cle: "titre_article", libelle: "Titre de l'article" },
  { cle: "numero_commande", libelle: "Numéro de commande" },
  { cle: "acheteur", libelle: "Pseudo de l'acheteur" },
  { cle: "date_limite", libelle: "Date limite d'envoi" },
  { cle: "lien_bordereau", libelle: "Lien du bordereau (texte ou URL du lien)" },
];

export const REGLE_VIDE: BrouillonRegle = {
  nom: "",
  type_cible: "autre",
  conditions: { expediteurs: ["vinted"] },
  extraction: {},
  priorite: 100,
  active: true,
};

const versListe = (v: string) =>
  v
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);

interface ResultatTest {
  nb_correspondances: number;
  exemples: { id: number; sujet: string | null; date: string | null; extraction: DonneesExtraites }[];
}

export function EditeurRegle({
  ouvert,
  setOuvert,
  initiale,
  emailId,
  apresEnregistrement,
}: {
  ouvert: boolean;
  setOuvert: (v: boolean) => void;
  initiale: BrouillonRegle;
  emailId?: number;
  apresEnregistrement?: () => void;
}) {
  const qc = useQueryClient();
  const [r, setR] = useState<BrouillonRegle>(initiale);
  const [listes, setListes] = useState({ expediteurs: "", sujet: "", corps: "" });
  const [test, setTest] = useState<ResultatTest | null>(null);

  useEffect(() => {
    if (!ouvert) return;
    setR(initiale);
    setListes({
      expediteurs: (initiale.conditions.expediteurs ?? []).join(", "),
      sujet: (initiale.conditions.sujet_contient ?? []).join(", "),
      corps: (initiale.conditions.corps_contient ?? []).join(", "),
    });
    setTest(null);
  }, [ouvert, initiale]);

  function corps() {
    const conditions = {
      ...r.conditions,
      expediteurs: versListe(listes.expediteurs),
      sujet_contient: versListe(listes.sujet),
      corps_contient: versListe(listes.corps),
    };
    const extraction = Object.fromEntries(Object.entries(r.extraction).filter(([, v]) => v));
    return { nom: r.nom, type_cible: r.type_cible, priorite: r.priorite, active: r.active, conditions, extraction };
  }

  const tester = useMutation({
    mutationFn: () =>
      api<ResultatTest>("/regles/tester", { body: { ...corps(), email_ids: emailId ? [emailId] : null } }),
    onSuccess: setTest,
    onError: (e: Error) => toast.error(e.message),
  });

  const enregistrer = useMutation({
    mutationFn: async () => {
      const regle = await api<Regle>(r.id ? `/regles/${r.id}` : "/regles", {
        method: r.id ? "PUT" : "POST",
        body: corps(),
      });
      // Les mails non classés sont reclassés avec la nouvelle règle.
      const { reclasses } = await api<{ reclasses: number }>("/regles/reappliquer", { method: "POST" });
      return { regle, reclasses };
    },
    onSuccess: ({ reclasses }) => {
      qc.invalidateQueries();
      toast.success(reclasses ? `Règle enregistrée · ${reclasses} mail(s) reclassé(s)` : "Règle enregistrée");
      setOuvert(false);
      apresEnregistrement?.();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Dialog open={ouvert} onOpenChange={setOuvert}>
      <DialogContent className="max-h-[92dvh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{r.id ? "Modifier la règle" : "Nouvelle règle"}</DialogTitle>
          <DialogDescription>
            Toutes les conditions remplies doivent correspondre. Dans une liste séparée par des virgules, un seul
            élément suffit (majuscules et accents ignorés).
          </DialogDescription>
        </DialogHeader>

        <div className="grid gap-3 sm:grid-cols-[1fr_180px_90px]">
          <Champ id="r-nom" libelle="Nom">
            <Input id="r-nom" value={r.nom} onChange={(e) => setR({ ...r, nom: e.target.value })} />
          </Champ>
          <Champ id="r-type" libelle="Type de mail">
            <Select value={r.type_cible} onValueChange={(v) => setR({ ...r, type_cible: v as TypeEmail })}>
              <SelectTrigger id="r-type" className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(TYPES_EMAIL).map(([v, l]) => (
                  <SelectItem key={v} value={v}>
                    {l}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Champ>
          <Champ id="r-priorite" libelle="Priorité">
            <Input
              id="r-priorite"
              inputMode="numeric"
              value={r.priorite}
              onChange={(e) => setR({ ...r, priorite: Number(e.target.value.replace(/\D/g, "")) || 0 })}
            />
          </Champ>
        </div>

        <fieldset className="space-y-3 rounded-lg border p-3">
          <legend className="px-1 text-sm font-medium">Conditions</legend>
          <Champ id="r-exp" libelle="L'expéditeur contient">
            <Input
              id="r-exp"
              value={listes.expediteurs}
              onChange={(e) => setListes({ ...listes, expediteurs: e.target.value })}
              placeholder="vinted"
            />
          </Champ>
          <Champ id="r-sujet" libelle="Le sujet contient">
            <Input
              id="r-sujet"
              value={listes.sujet}
              onChange={(e) => setListes({ ...listes, sujet: e.target.value })}
              placeholder="vendu, nouvelle commande"
            />
          </Champ>
          <Champ id="r-corps" libelle="Le corps contient">
            <Input
              id="r-corps"
              value={listes.corps}
              onChange={(e) => setListes({ ...listes, corps: e.target.value })}
            />
          </Champ>
          <div className="grid gap-3 sm:grid-cols-2">
            <Champ id="r-sregex" libelle="Regex sur le sujet">
              <Input
                id="r-sregex"
                className="font-mono text-xs"
                value={r.conditions.sujet_regex ?? ""}
                onChange={(e) => setR({ ...r, conditions: { ...r.conditions, sujet_regex: e.target.value } })}
              />
            </Champ>
            <Champ id="r-cregex" libelle="Regex sur le corps">
              <Input
                id="r-cregex"
                className="font-mono text-xs"
                value={r.conditions.corps_regex ?? ""}
                onChange={(e) => setR({ ...r, conditions: { ...r.conditions, corps_regex: e.target.value } })}
              />
            </Champ>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <Switch
              checked={!!r.conditions.piece_jointe_pdf}
              onCheckedChange={(v) => setR({ ...r, conditions: { ...r.conditions, piece_jointe_pdf: v } })}
            />
            Le mail contient un PDF
          </label>
        </fieldset>

        <fieldset className="space-y-2 rounded-lg border p-3">
          <legend className="px-1 text-sm font-medium">Extraction (regex, 1er groupe ou groupe nommé « v »)</legend>
          {CHAMPS_EXTRACTION.map((c) => (
            <div key={c.cle} className="grid items-center gap-1 sm:grid-cols-[200px_1fr] sm:gap-3">
              <label htmlFor={`x-${c.cle}`} className="text-sm text-muted-foreground">
                {c.libelle}
              </label>
              <Input
                id={`x-${c.cle}`}
                className="h-8 font-mono text-xs"
                value={r.extraction[c.cle] ?? ""}
                onChange={(e) => setR({ ...r, extraction: { ...r.extraction, [c.cle]: e.target.value } })}
              />
            </div>
          ))}
        </fieldset>

        <label className="flex items-center gap-2 text-sm">
          <Switch checked={r.active} onCheckedChange={(v) => setR({ ...r, active: v })} />
          Règle active
        </label>

        {test && (
          <div className="rounded-lg bg-muted/60 p-3 text-sm" role="status">
            <p className="font-medium">
              {test.nb_correspondances} mail(s) correspondent {emailId ? "(ce mail)" : "parmi les 200 derniers"}
            </p>
            <ul className="mt-2 space-y-1.5">
              {test.exemples.slice(0, 5).map((ex) => (
                <li key={ex.id} className="text-xs">
                  <span className="font-medium">{ex.sujet}</span>
                  <span className="block font-mono text-muted-foreground">
                    {Object.entries(ex.extraction)
                      .map(([k, v]) => `${k} = ${v}`)
                      .join(" · ") || "aucune donnée extraite"}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}

        <DialogFooter>
          <Button variant="outline" onClick={() => tester.mutate()} disabled={tester.isPending}>
            {tester.isPending ? <Loader2 className="animate-spin" /> : <FlaskConical />} Tester
          </Button>
          <Button onClick={() => enregistrer.mutate()} disabled={!r.nom.trim() || enregistrer.isPending}>
            {enregistrer.isPending && <Loader2 className="animate-spin" />}
            Enregistrer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
