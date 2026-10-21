"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Check, Columns3, Loader2, Star } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

import type { PhotoArticle } from "./photos-article";

interface Variante {
  id: number;
  photo_id: number;
  modele: string;
  statut: "en_cours" | "genere" | "erreur";
  cout_estime: string;
  duree_secondes: number | null;
  erreur: string | null;
}

interface Comparaison {
  modeles: string[];
  prix: Record<string, number | null>;
  en_cours: boolean;
  cout_total: string;
  lignes: { photo: PhotoArticle; variantes: Variante[] }[];
}

export const NOMS_MODELES: Record<string, { nom: string; note: string }> = {
  "openai/gpt-image-2:low": { nom: "GPT Image 2 · basse", note: "Recommandé, très économique" },
  "openai/gpt-image-2:medium": { nom: "GPT Image 2 · moyenne", note: "Plus de détails" },
  "bytedance/seedream-5-lite": { nom: "Seedream 5 Lite", note: "Haute résolution, textes fragiles" },
  "google/nano-banana-2": { nom: "Nano Banana 2", note: "Le plus fidèle, plus cher" },
};
const MODELES_PROPOSES = Object.keys(NOMS_MODELES);
const PRIX: Record<string, number> = {
  "openai/gpt-image-2:low": 0.012,
  "openai/gpt-image-2:medium": 0.047,
  "bytedance/seedream-5-lite": 0.035,
  "google/nano-banana-2": 0.067,
};
const LIBELLES: Record<string, string> = {
  devant: "Devant",
  dos: "Dos",
  etiquette: "Étiquette",
  logo: "Logo",
  detail: "Détail",
};

const dollars = (v: number | string) =>
  `${Number(v).toLocaleString("fr-FR", { minimumFractionDigits: 3, maximumFractionDigits: 3 })} $`;

export function ComparaisonModeles({
  articleId,
  nbPhotos,
  ouvert,
  setOuvert,
}: {
  articleId: number;
  nbPhotos: number;
  ouvert: boolean;
  setOuvert: (v: boolean) => void;
}) {
  const qc = useQueryClient();
  const [modeles, setModeles] = useState<string[]>(MODELES_PROPOSES);
  const [zoom, setZoom] = useState<{ src: string; titre: string } | null>(null);
  const cle = ["photos", articleId, "comparaison"];
  const { data } = useQuery({
    queryKey: cle,
    queryFn: () => api<Comparaison>(`/articles/${articleId}/photos/comparaison`),
    enabled: ouvert,
    refetchInterval: (q) => (q.state.data?.en_cours ? 3000 : false),
  });
  const rafraichir = () => {
    qc.invalidateQueries({ queryKey: cle });
    qc.invalidateQueries({ queryKey: ["photos", articleId] });
    qc.invalidateQueries({ queryKey: ["parametres", "photos"] });
  };

  const lancer = useMutation({
    mutationFn: () => api(`/articles/${articleId}/photos/comparer`, { body: { modeles } }),
    onSuccess: () => {
      toast.success("Comparaison lancée : les photos arrivent au fur et à mesure");
      rafraichir();
    },
    onError: (e: Error) => toast.error(e.message, { duration: 8000 }),
  });
  const choisir = useMutation({
    mutationFn: ({ id, defaut }: { id: number; defaut: boolean }) =>
      api(`/variantes/${id}/choisir`, { body: { defaut_pour_type: defaut } }),
    onSuccess: (_, v) => {
      toast.success(v.defaut ? "Photo choisie et modèle défini par défaut pour ce type" : "Photo choisie");
      rafraichir();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  async function choisirModelePartout(modele: string) {
    for (const ligne of data?.lignes ?? []) {
      const v = ligne.variantes.find((x) => x.modele === modele && x.statut === "genere");
      if (v) await choisir.mutateAsync({ id: v.id, defaut: true });
    }
  }

  const estimation = nbPhotos * modeles.reduce((t, m) => t + (PRIX[m] ?? 0.07), 0);
  const colonnes = data?.modeles.length ? data.modeles : [];

  return (
    <>
      <Dialog open={ouvert} onOpenChange={setOuvert}>
        <DialogContent className="max-h-[94dvh] overflow-y-auto sm:max-w-[min(1200px,96vw)]">
          <DialogHeader>
            <DialogTitle>Comparer les modèles</DialogTitle>
            <DialogDescription>
              Chaque photo est générée par chaque modèle avec la même disposition : seule la qualité du modèle change.
              Clique sur une image pour l&apos;agrandir.
            </DialogDescription>
          </DialogHeader>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-lg border bg-muted/30 p-3">
            {MODELES_PROPOSES.map((m) => (
              <label key={m} className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={modeles.includes(m)}
                  onCheckedChange={(v) => setModeles((ms) => (v ? [...ms, m] : ms.filter((x) => x !== m)))}
                />
                <span>
                  {NOMS_MODELES[m].nom} <span className="text-muted-foreground">~{dollars(PRIX[m])}</span>
                </span>
              </label>
            ))}
            <Button
              className="ml-auto"
              onClick={() => lancer.mutate()}
              disabled={!modeles.length || !nbPhotos || lancer.isPending || data?.en_cours}
            >
              {lancer.isPending || data?.en_cours ? <Loader2 className="animate-spin" /> : <Columns3 />}
              {data?.en_cours ? "Génération en cours…" : `Lancer la comparaison · ~${dollars(estimation)}`}
            </Button>
          </div>

          {!data?.lignes.length ? (
            <p className="py-10 text-center text-sm text-muted-foreground">
              Aucune comparaison pour cet article. Choisis les modèles puis lance la comparaison ({nbPhotos} photo
              {nbPhotos > 1 ? "s" : ""} × {modeles.length} modèle{modeles.length > 1 ? "s" : ""}).
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[760px] border-separate border-spacing-2 text-sm">
                <thead>
                  <tr>
                    <th className="w-24" />
                    <th className="text-left font-medium text-muted-foreground">Original</th>
                    {colonnes.map((m) => (
                      <th key={m} className="text-left align-bottom">
                        <p className="font-semibold">{NOMS_MODELES[m]?.nom ?? m}</p>
                        <p className="text-xs font-normal text-muted-foreground">
                          {NOMS_MODELES[m]?.note} · ~{dollars(data.prix[m] ?? 0)} / photo
                        </p>
                        <Button
                          variant="outline"
                          size="xs"
                          className="mt-1"
                          disabled={data.en_cours || choisir.isPending}
                          onClick={() => choisirModelePartout(m)}
                          title="Utiliser les photos de ce modèle et le définir par défaut pour ces types"
                        >
                          <Star /> Choisir partout + défaut
                        </Button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.lignes.map(({ photo, variantes }) => (
                    <tr key={photo.id}>
                      <td className="align-top text-sm font-medium">{LIBELLES[photo.type] ?? photo.type}</td>
                      <td className="w-[180px] align-top">
                        <button
                          type="button"
                          className="block w-full overflow-hidden rounded-lg border outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
                          onClick={() =>
                            setZoom({
                              src: `/api/photos/${photo.id}/fichier?version=original`,
                              titre: `${LIBELLES[photo.type]} · original`,
                            })
                          }
                        >
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={`/api/photos/${photo.id}/fichier?version=original`}
                            alt="Original"
                            className="aspect-[3/4] w-full object-cover"
                          />
                        </button>
                      </td>
                      {colonnes.map((m) => {
                        const v = variantes.find((x) => x.modele === m);
                        if (!v) return <td key={m} />;
                        const src = `/api/variantes/${v.id}/fichier`;
                        return (
                          <td key={m} className="w-[180px] align-top">
                            <div className="overflow-hidden rounded-lg border">
                              {v.statut === "genere" ? (
                                <button
                                  type="button"
                                  className="block w-full outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
                                  onClick={() =>
                                    setZoom({ src, titre: `${LIBELLES[photo.type]} · ${NOMS_MODELES[m]?.nom ?? m}` })
                                  }
                                >
                                  {/* eslint-disable-next-line @next/next/no-img-element */}
                                  <img
                                    src={src}
                                    alt={NOMS_MODELES[m]?.nom ?? m}
                                    className="aspect-[3/4] w-full object-cover"
                                    loading="lazy"
                                  />
                                </button>
                              ) : (
                                <div className="flex aspect-[3/4] flex-col items-center justify-center gap-2 bg-muted/40 p-2 text-center text-xs text-muted-foreground">
                                  {v.statut === "en_cours" ? (
                                    <>
                                      <Loader2 className="size-5 animate-spin text-brand" /> En cours…
                                    </>
                                  ) : (
                                    <>
                                      <AlertCircle className="size-5 text-destructive" /> {v.erreur}
                                    </>
                                  )}
                                </div>
                              )}
                            </div>
                            {v.statut === "genere" && (
                              <div className="mt-1 flex items-center justify-between gap-1">
                                <span className="text-[11px] text-muted-foreground tabular-nums">
                                  {v.duree_secondes ? `${Math.round(v.duree_secondes)} s` : ""}
                                </span>
                                <Button
                                  size="xs"
                                  variant={
                                    photo.modele === v.modele && photo.version_choisie === "genere"
                                      ? "secondary"
                                      : "outline"
                                  }
                                  disabled={choisir.isPending}
                                  onClick={() => choisir.mutate({ id: v.id, defaut: false })}
                                  className={cn(photo.modele === v.modele && "border-brand text-brand")}
                                >
                                  <Check /> Utiliser
                                </Button>
                              </div>
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="mt-2 text-xs text-muted-foreground">
                Coût de cette comparaison : {dollars(data.cout_total)}. « Choisir partout + défaut » utilise ce modèle
                pour les prochaines retouches de ces types (modifiable dans Paramètres → Photos).
              </p>
            </div>
          )}
        </DialogContent>
      </Dialog>

      <Dialog open={!!zoom} onOpenChange={(o) => !o && setZoom(null)}>
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>{zoom?.titre}</DialogTitle>
          </DialogHeader>
          {zoom && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={zoom.src} alt={zoom.titre} className="max-h-[78dvh] w-full rounded-lg object-contain" />
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
