"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Save } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { LignesSquelette } from "@/components/commun";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";

type Reglages = Record<string, Record<string, unknown>>;
type TypeChamp = "nombre" | "texte" | "lignes" | "bool";

interface Champ {
  cle: string;
  libelle: string;
  type: TypeChamp;
  aide?: string;
  pas?: number;
}

const MODULES: Record<string, string> = {
  brouillons: "Brouillons automatiques",
  assistant: "Assistant (messages et offres reçues)",
  favoris: "Message et offre aux favoris",
  republication: "Republication",
  prix: "Baisse de prix",
  apres_vente: "Après-vente",
};

const SECTIONS: { cle: string; titre: string; champs: Champ[] }[] = [
  {
    cle: "heures",
    titre: "Heures actives (heure de Paris)",
    champs: [
      { cle: "debut", libelle: "Début", type: "nombre", aide: "La nuit, seules les réponses aux acheteurs partent." },
      { cle: "fin", libelle: "Fin", type: "nombre" },
    ],
  },
  {
    cle: "budget",
    titre: "Budget d'actions",
    champs: [
      { cle: "republications_jour", libelle: "Republications par jour", type: "nombre" },
      { cle: "offres_jour", libelle: "Offres envoyées par jour", type: "nombre" },
      { cle: "messages_jour", libelle: "Messages par jour", type: "nombre", aide: "Favoris, réponses, après-vente." },
      { cle: "actions_heure", libelle: "Actions par heure (toutes confondues)", type: "nombre" },
    ],
  },
  {
    cle: "brouillons",
    titre: "Brouillons",
    champs: [{ cle: "max_jour", libelle: "Maximum par jour", type: "nombre" }],
  },
  {
    cle: "assistant",
    titre: "Assistant",
    champs: [
      { cle: "seuil_acceptation_pct", libelle: "Accepter dès (% du prix affiché)", type: "nombre" },
      { cle: "seuil_refus_pct", libelle: "Refuser sous (% du prix affiché)", type: "nombre" },
      { cle: "ton", libelle: "Ton des réponses", type: "texte", aide: "Ex. : « tutoiement, chaleureux »." },
      { cle: "reponses_types", libelle: "Réponses types (une par ligne)", type: "lignes" },
    ],
  },
  {
    cle: "prix",
    titre: "Prix",
    champs: [
      { cle: "baisse_pct", libelle: "Baisse unique (%)", type: "nombre" },
      { cle: "delai_min_heures", libelle: "Après (heures, minimum)", type: "nombre" },
      { cle: "delai_max_heures", libelle: "Après (heures, maximum)", type: "nombre" },
      {
        cle: "plancher_pct",
        libelle: "Plancher (% du prix initial)",
        type: "nombre",
        aide: "Jamais d'offre en dessous.",
      },
    ],
  },
  {
    cle: "favoris",
    titre: "Favoris",
    champs: [
      {
        cle: "messages",
        libelle: "Messages (un par ligne, tiré au hasard)",
        type: "lignes",
        aide: "Variables : {prenom} (pseudo Vinted), {article}, {prix}.",
      },
      { cle: "reduction_pct", libelle: "Réduction proposée (%)", type: "nombre" },
      { cle: "delai_min_s", libelle: "Délai minimum (s)", type: "nombre" },
      { cle: "delai_max_s", libelle: "Délai maximum (s)", type: "nombre" },
    ],
  },
  {
    cle: "republication",
    titre: "Republication",
    champs: [
      { cle: "cadence_jours", libelle: "Tous les (jours)", type: "nombre" },
      {
        cle: "conversation_active_minutes",
        libelle: "Reportée si message depuis moins de (min)",
        type: "nombre",
      },
      { cle: "rotation_min", libelle: "Rotation min (°)", type: "nombre", pas: 0.1 },
      { cle: "rotation_max", libelle: "Rotation max (°)", type: "nombre", pas: 0.1 },
      { cle: "zoom_min", libelle: "Zoom min (%)", type: "nombre", pas: 0.1 },
      { cle: "zoom_max", libelle: "Zoom max (%)", type: "nombre", pas: 0.1 },
      { cle: "luminosite_min", libelle: "Baisse de luminosité min (%)", type: "nombre", pas: 0.1 },
      { cle: "luminosite_max", libelle: "Baisse de luminosité max (%)", type: "nombre", pas: 0.1 },
      { cle: "qualite_min", libelle: "Qualité JPEG min", type: "nombre" },
      { cle: "qualite_max", libelle: "Qualité JPEG max", type: "nombre" },
    ],
  },
  {
    cle: "apres_vente",
    titre: "Après-vente",
    champs: [
      { cle: "messages", libelle: "Messages de remerciement (un par ligne)", type: "lignes" },
      { cle: "heure_recap", libelle: "Heure du récapitulatif (HH:MM)", type: "texte" },
    ],
  },
];

function versSaisie(v: unknown, type: TypeChamp): string | boolean {
  if (type === "bool") return Boolean(v);
  if (type === "lignes") return Array.isArray(v) ? v.join("\n") : "";
  return v === null || v === undefined ? "" : String(v).replace(".", ",");
}

function depuisSaisie(v: string | boolean, type: TypeChamp): unknown {
  if (type === "bool") return Boolean(v);
  if (type === "lignes")
    return String(v)
      .split("\n")
      .map((l) => l.trim())
      .filter(Boolean);
  if (type === "nombre") return Number(String(v).replace(",", "."));
  return String(v);
}

/** Tous les réglages d'un compte, section par section (enregistrement partiel). */
export function ReglagesCompte({
  compteId,
  nom,
  ouvert,
  onClose,
}: {
  compteId: number;
  nom: string;
  ouvert: boolean;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["automatisation", "reglages", compteId],
    queryFn: () =>
      api<Reglages & { notifications: { types: Record<string, boolean> } }>(
        `/automatisation/comptes/${compteId}/reglages`,
      ),
    enabled: ouvert,
  });
  const global = useQuery({
    queryKey: ["automatisation", "global"],
    queryFn: () => api<{ types_alertes: Record<string, string> }>("/automatisation/global"),
    enabled: ouvert,
  });
  const [saisie, setSaisie] = useState<Record<string, Record<string, string | boolean>>>({});

  useEffect(() => {
    if (!data) return;
    setSaisie(
      Object.fromEntries(
        SECTIONS.map((s) => [
          s.cle,
          Object.fromEntries(s.champs.map((c) => [c.cle, versSaisie(data[s.cle]?.[c.cle], c.type)])),
        ]),
      ),
    );
  }, [data]);

  const enregistrer = useMutation({
    mutationFn: (corps: Record<string, unknown>) =>
      api<Reglages>(`/automatisation/comptes/${compteId}/reglages`, { method: "PUT", body: corps }),
    onSuccess: (r) => {
      qc.setQueryData(["automatisation", "reglages", compteId], r);
      qc.invalidateQueries({ queryKey: ["automatisation", "comptes"] });
      toast.success("Réglages enregistrés");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  return (
    <Sheet open={ouvert} onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
        <SheetHeader>
          <SheetTitle>Réglages : {nom}</SheetTitle>
          <SheetDescription>
            Relus par l&apos;extension avant chaque action. Chaque section s&apos;enregistre séparément.
          </SheetDescription>
        </SheetHeader>
        {!data ? (
          <div className="p-4">
            <LignesSquelette n={8} />
          </div>
        ) : (
          <div className="space-y-6 px-4 pb-8">
            <section className="space-y-2">
              <h3 className="text-sm font-semibold">Modules</h3>
              {Object.entries(MODULES).map(([cle, libelle]) => (
                <label key={cle} className="flex items-center justify-between gap-3 text-sm">
                  {libelle}
                  <Switch
                    checked={Boolean((data.modules as Record<string, boolean>)[cle])}
                    onCheckedChange={(v) => enregistrer.mutate({ modules: { [cle]: v } })}
                  />
                </label>
              ))}
            </section>
            {SECTIONS.map((s) => (
              <form
                key={s.cle}
                className="space-y-3 border-t pt-4"
                onSubmit={(e) => {
                  e.preventDefault();
                  const valeurs = saisie[s.cle] ?? {};
                  enregistrer.mutate({
                    [s.cle]: Object.fromEntries(
                      s.champs.map((c) => [c.cle, depuisSaisie(valeurs[c.cle] ?? "", c.type)]),
                    ),
                  });
                }}
              >
                <h3 className="text-sm font-semibold">{s.titre}</h3>
                <div className="grid gap-3 sm:grid-cols-2">
                  {s.champs.map((c) => {
                    const id = `${compteId}-${s.cle}-${c.cle}`;
                    const valeur = saisie[s.cle]?.[c.cle] ?? "";
                    const maj = (v: string) => setSaisie((x) => ({ ...x, [s.cle]: { ...x[s.cle], [c.cle]: v } }));
                    return (
                      <div
                        key={c.cle}
                        className={c.type === "lignes" || c.type === "texte" ? "space-y-1 sm:col-span-2" : "space-y-1"}
                      >
                        <label htmlFor={id} className="text-xs text-muted-foreground">
                          {c.libelle}
                        </label>
                        {c.type === "lignes" ? (
                          <Textarea id={id} rows={3} value={String(valeur)} onChange={(e) => maj(e.target.value)} />
                        ) : (
                          <Input
                            id={id}
                            inputMode={c.type === "nombre" ? "decimal" : undefined}
                            value={String(valeur)}
                            onChange={(e) => maj(e.target.value)}
                          />
                        )}
                        {c.aide && <p className="text-[11px] text-muted-foreground">{c.aide}</p>}
                      </div>
                    );
                  })}
                </div>
                <Button type="submit" size="sm" variant="outline" disabled={enregistrer.isPending}>
                  {enregistrer.isPending ? <Loader2 className="animate-spin" /> : <Save />} Enregistrer
                </Button>
              </form>
            ))}
            <section className="space-y-2 border-t pt-4">
              <h3 className="text-sm font-semibold">Alertes Telegram</h3>
              {Object.entries(global.data?.types_alertes ?? {}).map(([cle, libelle]) => (
                <label key={cle} className="flex items-center justify-between gap-3 text-sm">
                  {libelle}
                  <Switch
                    checked={Boolean(data.notifications.types[cle])}
                    onCheckedChange={(v) => enregistrer.mutate({ notifications: { types: { [cle]: v } } })}
                  />
                </label>
              ))}
            </section>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
