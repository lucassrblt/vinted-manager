"use client";

import { useMutation } from "@tanstack/react-query";
import { ImagePlus, Loader2, Sparkles, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";

import { EnTetePage } from "@/components/commun";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useInvaliderStock } from "@/lib/queries";
import { cn } from "@/lib/utils";

const MAX_PHOTOS = 12;

export default function NouvelleAnnonce() {
  const router = useRouter();
  const invalider = useInvaliderStock();
  const [fichiers, setFichiers] = useState<File[]>([]);
  const apercus = useMemo(() => fichiers.map((f) => URL.createObjectURL(f)), [fichiers]);
  useEffect(() => () => apercus.forEach((u) => URL.revokeObjectURL(u)), [apercus]);

  const creation = useMutation({
    mutationFn: () => {
      const form = new FormData();
      for (const f of fichiers) form.append("photos", f);
      return api<{ article_id: number; erreur_ia: string | null; retouche_lancee: boolean }>("/annonces/nouvelle", {
        form,
      });
    },
    onSuccess: (r) => {
      invalider();
      if (r.erreur_ia) toast.error(`${r.erreur_ia} Complète la fiche à la main.`, { duration: 8000 });
      router.push(`/annonces/${r.article_id}?nouvelle=1`);
    },
    onError: (e: Error) => toast.error(e.message, { duration: 8000 }),
  });

  const { getRootProps, getInputProps, isDragActive, open } = useDropzone({
    accept: { "image/jpeg": [".jpg", ".jpeg"], "image/png": [".png"], "image/webp": [".webp"] },
    noClick: fichiers.length > 0,
    disabled: creation.isPending,
    onDrop: (ok, refus) => {
      if (refus.length) toast.error("Seules les photos JPG, PNG ou WEBP sont acceptées.");
      setFichiers((f) => {
        const tous = [...f, ...ok];
        if (tous.length > MAX_PHOTOS) toast.error(`${MAX_PHOTOS} photos maximum : les suivantes sont ignorées.`);
        return tous.slice(0, MAX_PHOTOS);
      });
    },
  });

  return (
    <>
      <EnTetePage
        titre="Nouvelle annonce"
        description="Dépose les photos de l'article : l'IA les trie, lit l'étiquette, rédige l'annonce et retouche les photos."
      />
      <div className="mx-auto max-w-4xl space-y-4">
        <div
          {...getRootProps()}
          className={cn(
            "rounded-2xl border-2 border-dashed bg-card p-6 transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
            isDragActive ? "border-brand bg-brand-soft/40" : "border-border",
            !fichiers.length && "cursor-pointer hover:bg-muted/40",
          )}
        >
          <input {...getInputProps()} aria-label="Photos de l'article" />
          {!fichiers.length ? (
            <div className="flex flex-col items-center gap-3 py-14 text-center">
              <span className="flex size-14 items-center justify-center rounded-full bg-brand-soft text-brand">
                <ImagePlus className="size-7" />
              </span>
              <p className="text-lg font-medium">Glisse toutes les photos de l&apos;article ici</p>
              <p className="max-w-md text-sm text-muted-foreground">
                Devant, dos, étiquette, logo, et les défauts éventuels, dans n&apos;importe quel ordre. Les photos de
                défaut ne sont jamais retouchées.
              </p>
              <Button type="button" variant="outline" className="mt-2">
                Choisir les photos
              </Button>
            </div>
          ) : (
            <div className="space-y-4">
              <ul className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-6">
                {fichiers.map((f, i) => (
                  <li key={`${f.name}-${i}`} className="group relative">
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={apercus[i]} alt={f.name} className="aspect-[3/4] w-full rounded-lg border object-cover" />
                    {!creation.isPending && (
                      <button
                        type="button"
                        onClick={() => setFichiers((l) => l.filter((_, j) => j !== i))}
                        className="absolute top-1 right-1 rounded-full bg-background/90 p-1 opacity-0 shadow transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
                        aria-label={`Retirer ${f.name}`}
                      >
                        <X className="size-3.5" />
                      </button>
                    )}
                  </li>
                ))}
                {fichiers.length < MAX_PHOTOS && !creation.isPending && (
                  <li>
                    <button
                      type="button"
                      onClick={open}
                      className="flex aspect-[3/4] w-full flex-col items-center justify-center gap-1 rounded-lg border border-dashed text-xs text-muted-foreground hover:bg-muted/50"
                    >
                      <ImagePlus className="size-5" /> Ajouter
                    </button>
                  </li>
                )}
              </ul>
              <div className="flex flex-wrap items-center justify-between gap-3 border-t pt-4">
                <p className="text-sm text-muted-foreground">
                  {creation.isPending
                    ? "L'IA regarde tes photos et lit l'étiquette… (une dizaine de secondes)"
                    : `${fichiers.length} photo${fichiers.length > 1 ? "s" : ""}`}
                </p>
                <div className="flex gap-2">
                  {!creation.isPending && (
                    <Button type="button" variant="ghost" onClick={() => setFichiers([])}>
                      Tout retirer
                    </Button>
                  )}
                  <Button
                    type="button"
                    size="lg"
                    className="bg-brand text-brand-foreground hover:bg-brand/90"
                    disabled={creation.isPending}
                    onClick={() => creation.mutate()}
                  >
                    {creation.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />}
                    Créer l&apos;annonce
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
        <p className="text-center text-xs text-muted-foreground">
          Ensuite : tu relis le titre et la description, tu choisis la provenance (stock, batch ou pièce perso) et tu
          copies tout sur Vinted.
        </p>
      </div>
    </>
  );
}
