"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ImagePlus, Loader2 } from "lucide-react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";

import { LignesSquelette } from "@/components/commun";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import { cn } from "@/lib/utils";

interface ParametresPhotos {
  modele: string;
  fond_defini: boolean;
  configure: boolean;
  modeles: Record<string, number>;
  depense_mois: string;
  photos_generees_mois: number;
}

const NOMS: Record<string, string> = {
  "google/nano-banana-2": "Nano Banana 2 — le plus fidèle (recommandé)",
  "bytedance/seedream-5-lite": "Seedream 5 Lite — moins cher, textes d'étiquette moins fiables",
  "bytedance/seedream-4.5": "Seedream 4.5",
  "black-forest-labs/flux-2-pro": "FLUX.2 Pro",
  "qwen/qwen-image-edit-plus": "Qwen Image Edit Plus",
};

export function ParametresPhotosIa() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["parametres", "photos"],
    queryFn: () => api<ParametresPhotos>("/parametres/photos"),
  });
  const maj = (r: ParametresPhotos) => qc.setQueryData(["parametres", "photos"], r);
  const modele = useMutation({
    mutationFn: (m: string) => api<ParametresPhotos>("/parametres/photos", { method: "PUT", body: { modele: m } }),
    onSuccess: (r) => {
      maj(r);
      toast.success("Modèle enregistré");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const fond = useMutation({
    mutationFn: (f: File) => {
      const form = new FormData();
      form.append("fichier", f);
      return api<ParametresPhotos>("/parametres/photos/fond", { form });
    },
    onSuccess: (r) => {
      maj(r);
      toast.success("Photo du tapis enregistrée");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: { "image/jpeg": [".jpg", ".jpeg"], "image/png": [".png"], "image/webp": [".webp"] },
    multiple: false,
    onDrop: (ok) => ok[0] && fond.mutate(ok[0]),
  });

  if (!data) return <LignesSquelette n={4} />;
  const prix = data.modeles[data.modele] ?? 0;

  return (
    <div className="grid max-w-5xl gap-5 lg:grid-cols-[1fr_320px]">
      <section className="space-y-5 rounded-xl border bg-card p-5">
        {!data.configure && (
          <p className="rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
            Ajoute REPLICATE_API_TOKEN aux variables du serveur pour activer la retouche des photos.
          </p>
        )}
        <div className="space-y-1.5">
          <label htmlFor="modele-photos" className="text-sm font-medium">
            Modèle de retouche
          </label>
          <Select value={data.modele} onValueChange={(m) => modele.mutate(m)}>
            <SelectTrigger id="modele-photos" className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {Object.entries(data.modeles).map(([m, p]) => (
                <SelectItem key={m} value={m}>
                  {NOMS[m] ?? m} · ~{p.toLocaleString("fr-FR")} $ / photo
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">
            Environ {(prix * 4).toLocaleString("fr-FR", { maximumFractionDigits: 2 })} $ par article de 4 photos.
          </p>
        </div>

        <div className="space-y-2">
          <p className="text-sm font-medium">Photo du tapis (fond de toutes les photos)</p>
          <p className="text-xs text-muted-foreground">
            Une photo prise de dessus, le tapis seul remplissant tout le cadre, à la lumière du jour.
          </p>
          <div className="grid grid-cols-[140px_1fr] gap-3">
            <div className="aspect-[3/4] overflow-hidden rounded-lg border bg-muted">
              {data.fond_defini && (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={`/api/parametres/photos/fond?v=${fond.submittedAt}`}
                  alt="Tapis de référence"
                  className="size-full object-cover"
                />
              )}
            </div>
            <div
              {...getRootProps()}
              className={cn(
                "flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed p-4 text-center text-sm outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                isDragActive ? "border-brand bg-brand-soft" : "hover:bg-muted/50",
              )}
            >
              <input {...getInputProps()} aria-label="Photo du tapis" />
              {fond.isPending ? (
                <Loader2 className="size-5 animate-spin" />
              ) : (
                <ImagePlus className="size-5 text-muted-foreground" />
              )}
              {data.fond_defini ? "Remplacer la photo du tapis" : "Déposer la photo du tapis"}
            </div>
          </div>
        </div>
      </section>

      <section className="space-y-2 rounded-xl border bg-card p-5 text-sm">
        <h2 className="font-semibold">Ce mois-ci</h2>
        <p className="text-2xl font-semibold tabular-nums">
          {Number(data.depense_mois).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $
        </p>
        <p className="text-muted-foreground">
          {data.photos_generees_mois} photo(s) retouchée(s) · estimation selon le prix du modèle
        </p>
      </section>
    </div>
  );
}
