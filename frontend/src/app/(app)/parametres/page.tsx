"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { toast } from "sonner";

import { EnTetePage, LignesSquelette } from "@/components/commun";
import { ConfigurationImap } from "@/components/mails/config-imap";
import { Champ } from "@/components/stock/dialog-article";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { saisieVersDecimal } from "@/lib/format";
import { useParametres } from "@/lib/queries";
import type { Parametres } from "@/lib/types";

const CHAMPS: { cle: keyof Parametres; libelle: string; aide: string; type: "decimal" | "entier" | "pourcent" }[] = [
  {
    cle: "taux_cotisations",
    libelle: "Taux de cotisations (%)",
    aide: "Appliqué au CA encaissé. Micro-entreprise vente : 12,3 %.",
    type: "pourcent",
  },
  {
    cle: "coefficient_min",
    libelle: "Coefficient minimum",
    aide: "En dessous : « Sous l'objectif ».",
    type: "decimal",
  },
  { cle: "coefficient_max", libelle: "Coefficient maximum", aide: "Au-dessus : « Au-dessus ».", type: "decimal" },
  {
    cle: "seuil_article_lent_jours",
    libelle: "Article lent après (jours)",
    aide: "Signalé sur l'écran du jour avec une suggestion de prix.",
    type: "entier",
  },
  {
    cle: "objectif_ventes_jour",
    libelle: "Objectif de ventes par jour",
    aide: "Affiché sur l'écran du jour.",
    type: "entier",
  },
  {
    cle: "arrondi_seuil",
    libelle: "Seuil d'arrondi du prix conseillé (€)",
    aide: "En dessous : arrondi à l'euro.",
    type: "decimal",
  },
  {
    cle: "arrondi_pas",
    libelle: "Pas d'arrondi au-dessus du seuil (€)",
    aide: "Par défaut, multiple de 5 €.",
    type: "decimal",
  },
];

function versSaisie(p: Parametres, cle: keyof Parametres, type: string): string {
  const v = p[cle];
  if (type === "pourcent") return String(Math.round(Number(v) * 10000) / 100).replace(".", ",");
  return String(Number(v)).replace(".", ",");
}

export default function PageParametres() {
  return (
    <Suspense fallback={<LignesSquelette n={6} />}>
      <ContenuParametres />
    </Suspense>
  );
}

function ContenuParametres() {
  const ongletInitial = useSearchParams().get("onglet") ?? "general";
  const qc = useQueryClient();
  const { data } = useParametres();
  const [valeurs, setValeurs] = useState<Record<string, string>>({});

  useEffect(() => {
    if (data) setValeurs(Object.fromEntries(CHAMPS.map((c) => [c.cle, versSaisie(data, c.cle, c.type)])));
  }, [data]);

  const erreurs = Object.fromEntries(
    CHAMPS.map((c) => {
      const d = saisieVersDecimal(valeurs[c.cle] ?? "");
      if (d === null || Number(d) < 0) return [c.cle, "Valeur invalide."];
      if (c.type === "entier" && !Number.isInteger(Number(d))) return [c.cle, "Nombre entier attendu."];
      if (c.type === "pourcent" && Number(d) > 100) return [c.cle, "Maximum 100 %."];
      return [c.cle, null];
    }),
  );
  const coeffIncoherent =
    Number(saisieVersDecimal(valeurs.coefficient_min ?? "")) >=
    Number(saisieVersDecimal(valeurs.coefficient_max ?? ""));

  const enregistrer = useMutation({
    mutationFn: () =>
      api<Parametres>("/parametres", {
        method: "PATCH",
        body: Object.fromEntries(
          CHAMPS.map((c) => {
            const d = Number(saisieVersDecimal(valeurs[c.cle]));
            return [c.cle, c.type === "pourcent" ? String(d / 100) : c.type === "entier" ? d : String(d)];
          }),
        ),
      }),
    onSuccess: () => {
      qc.invalidateQueries();
      toast.success("Paramètres enregistrés");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <>
      <EnTetePage titre="Paramètres" />
      <Tabs defaultValue={ongletInitial}>
        <TabsList>
          <TabsTrigger value="general">Général</TabsTrigger>
          <TabsTrigger value="mails">Mails</TabsTrigger>
          <TabsTrigger value="notifications" disabled>
            Notifications (étape 4)
          </TabsTrigger>
        </TabsList>
        <TabsContent value="general" className="mt-5">
          {!data ? (
            <LignesSquelette n={6} />
          ) : (
            <form
              className="max-w-2xl space-y-6 rounded-xl border bg-card p-5"
              onSubmit={(e) => {
                e.preventDefault();
                enregistrer.mutate();
              }}
            >
              <div className="grid gap-5 sm:grid-cols-2">
                {CHAMPS.map((c) => (
                  <Champ key={c.cle} id={c.cle} libelle={c.libelle} erreur={erreurs[c.cle]}>
                    <Input
                      id={c.cle}
                      inputMode="decimal"
                      value={valeurs[c.cle] ?? ""}
                      onChange={(e) => setValeurs((v) => ({ ...v, [c.cle]: e.target.value }))}
                      aria-describedby={`${c.cle}-aide`}
                    />
                    <p id={`${c.cle}-aide`} className="text-xs text-muted-foreground">
                      {c.aide}
                    </p>
                  </Champ>
                ))}
              </div>
              {coeffIncoherent && (
                <p className="text-sm text-destructive">Le coefficient minimum doit être inférieur au maximum.</p>
              )}
              <div className="flex justify-end">
                <Button
                  type="submit"
                  disabled={enregistrer.isPending || coeffIncoherent || Object.values(erreurs).some(Boolean)}
                >
                  {enregistrer.isPending && <Loader2 className="animate-spin" />}
                  Enregistrer
                </Button>
              </div>
            </form>
          )}
        </TabsContent>
        <TabsContent value="mails" className="mt-5">
          <ConfigurationImap />
        </TabsContent>
      </Tabs>
    </>
  );
}
