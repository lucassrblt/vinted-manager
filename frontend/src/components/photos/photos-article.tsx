"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, Download, ImagePlus, Loader2, RefreshCw, Sparkles, Trash2, Wand2 } from "lucide-react";
import Link from "next/link";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { api, telecharger } from "@/lib/api";
import { cn } from "@/lib/utils";

export type TypePhoto = "devant" | "dos" | "etiquette" | "logo" | "detail" | "defaut";

export interface PhotoArticle {
  id: number;
  type: TypePhoto;
  statut: "a_generer" | "en_cours" | "genere" | "erreur" | "original";
  version_choisie: "genere" | "original";
  a_version_generee: boolean;
  nb_generations: number;
  cout_estime: string;
  erreur: string | null;
  updated_at: string;
}

interface EtatPhotos {
  photos: PhotoArticle[];
  manquantes: TypePhoto[];
  en_cours: boolean;
  cout_total: string;
}

const LIBELLES: Record<TypePhoto, string> = {
  devant: "Devant",
  dos: "Dos",
  etiquette: "Étiquette",
  logo: "Logo",
  detail: "Détail",
  defaut: "Défaut",
};
const OBLIGATOIRES: TypePhoto[] = ["devant", "dos", "etiquette", "logo"];
const ACCEPTES = { "image/jpeg": [".jpg", ".jpeg"], "image/png": [".png"], "image/webp": [".webp"] };

const dollars = (v: string | number) =>
  `${Number(v).toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} $`;

function urlImage(p: PhotoArticle, version: "choisie" | "original" | "genere" = "choisie") {
  return `/api/photos/${p.id}/fichier?version=${version}&v=${encodeURIComponent(p.updated_at)}`;
}

function CartePhoto({ photo, onChange }: { photo: PhotoArticle; onChange: () => void }) {
  const action = useMutation({
    mutationFn: (corps: { methode: string; chemin: string; body?: unknown }) =>
      api(corps.chemin, { method: corps.methode, body: corps.body }),
    onSuccess: onChange,
    onError: (e: Error) => toast.error(e.message),
  });
  const enCours = photo.statut === "en_cours";
  return (
    <figure className="group relative overflow-hidden rounded-xl border bg-muted/30">
      <div className="relative aspect-[3/4]">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={urlImage(photo)}
          alt={`Photo ${LIBELLES[photo.type]}`}
          className="size-full object-cover"
          loading="lazy"
        />
        {enCours && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-background/70 text-sm backdrop-blur-sm">
            <Loader2 className="size-5 animate-spin text-brand" />
            Retouche en cours…
          </div>
        )}
        <span className="absolute top-2 left-2 rounded-full bg-background/90 px-2 py-0.5 text-xs font-medium shadow-sm">
          {LIBELLES[photo.type]}
        </span>
        {photo.version_choisie === "genere" && photo.a_version_generee && !enCours && (
          <span className="absolute bottom-2 left-2 flex items-center gap-1 rounded-full bg-brand px-2 py-0.5 text-xs font-medium text-brand-foreground shadow-sm">
            <Sparkles className="size-3" /> Retouchée
          </span>
        )}
      </div>
      <figcaption className="space-y-2 p-2">
        {photo.statut === "erreur" && (
          <p className="flex items-start gap-1 text-xs text-destructive">
            <AlertCircle className="mt-0.5 size-3.5 shrink-0" /> {photo.erreur}
          </p>
        )}
        {photo.type === "defaut" ? (
          <p className="text-xs text-muted-foreground">Photo originale, jamais retouchée.</p>
        ) : (
          <div className="flex flex-wrap items-center gap-1">
            {photo.a_version_generee && (
              <div className="flex rounded-md border p-0.5 text-xs" role="group" aria-label="Version à utiliser">
                {(["original", "genere"] as const).map((v) => (
                  <button
                    key={v}
                    type="button"
                    disabled={enCours}
                    onClick={() =>
                      action.mutate({ methode: "PATCH", chemin: `/photos/${photo.id}`, body: { version_choisie: v } })
                    }
                    className={cn(
                      "rounded px-2 py-0.5 outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
                      photo.version_choisie === v
                        ? "bg-foreground text-background"
                        : "text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {v === "original" ? "Originale" : "Retouchée"}
                  </button>
                ))}
              </div>
            )}
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label={photo.a_version_generee ? "Régénérer" : "Générer"}
              title={photo.a_version_generee ? "Régénérer (nouvelle disposition)" : "Générer"}
              disabled={enCours || action.isPending}
              onClick={() => action.mutate({ methode: "POST", chemin: `/photos/${photo.id}/regenerer` })}
            >
              <RefreshCw />
            </Button>
            {photo.a_version_generee && (
              <Button
                variant="ghost"
                size="xs"
                title="Régénérer avec le modèle haute qualité (~0,07 $), si la photo ne convient pas"
                disabled={enCours || action.isPending}
                onClick={() => action.mutate({ methode: "POST", chemin: `/photos/${photo.id}/regenerer?premium=true` })}
              >
                <Sparkles /> HQ
              </Button>
            )}
          </div>
        )}
        <div className="flex items-center justify-between text-[11px] text-muted-foreground">
          <span>
            {photo.nb_generations ? `${photo.nb_generations} génération(s) · ${dollars(photo.cout_estime)}` : " "}
          </span>
          <Button
            variant="ghost"
            size="icon-xs"
            aria-label="Supprimer la photo"
            disabled={enCours}
            onClick={() =>
              confirm("Supprimer cette photo ?") && action.mutate({ methode: "DELETE", chemin: `/photos/${photo.id}` })
            }
          >
            <Trash2 />
          </Button>
        </div>
      </figcaption>
    </figure>
  );
}

function ZoneDepot({
  libelle,
  aide,
  onFichiers,
  multiple = false,
  occupe,
  className,
}: {
  libelle: string;
  aide?: string;
  onFichiers: (f: File[]) => void;
  multiple?: boolean;
  occupe?: boolean;
  className?: string;
}) {
  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: ACCEPTES,
    multiple,
    maxSize: 15 * 1024 * 1024,
    onDrop: (ok, refus) => {
      if (refus.length) toast.error("Photo refusée : JPG, PNG ou WEBP de 15 Mo maximum.");
      if (ok.length) onFichiers(ok);
    },
  });
  return (
    <div
      {...getRootProps()}
      className={cn(
        "flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed p-3 text-center text-sm transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
        isDragActive ? "border-brand bg-brand-soft" : "hover:bg-muted/50",
        className,
      )}
    >
      <input {...getInputProps()} aria-label={libelle} />
      {occupe ? (
        <Loader2 className="size-5 animate-spin text-muted-foreground" />
      ) : (
        <ImagePlus className="size-5 text-muted-foreground" />
      )}
      <span className="font-medium">{libelle}</span>
      {aide && <span className="text-xs text-muted-foreground">{aide}</span>}
    </div>
  );
}

export function PhotosArticle({ articleId }: { articleId: number }) {
  const qc = useQueryClient();
  const cle = ["photos", articleId];
  const { data } = useQuery({
    queryKey: cle,
    queryFn: () => api<EtatPhotos>(`/articles/${articleId}/photos`),
    refetchInterval: (q) => (q.state.data?.en_cours ? 3000 : false),
  });
  const config = useQuery({
    queryKey: ["parametres", "photos"],
    queryFn: () => api<{ fond_defini: boolean; configure: boolean; cout_article: number }>("/parametres/photos"),
    staleTime: 60_000,
  });
  const rafraichir = () => qc.invalidateQueries({ queryKey: cle });

  const depot = useMutation({
    mutationFn: async (lots: { fichier: File; type: TypePhoto }[]) => {
      for (const { fichier, type } of lots) {
        const form = new FormData();
        form.append("fichier", fichier);
        form.append("type", type);
        await api(`/articles/${articleId}/photos`, { form });
      }
    },
    onSuccess: rafraichir,
    onError: (e: Error) => {
      toast.error(e.message);
      rafraichir();
    },
  });
  const generation = useMutation({
    mutationFn: () => api<PhotoArticle[]>(`/articles/${articleId}/photos/generer`, { method: "POST" }),
    onSuccess: (r) => {
      toast.success(`${r.length} photo(s) en cours de retouche (environ 10 s chacune)`);
      rafraichir();
    },
    onError: (e: Error) => toast.error(e.message, { duration: 8000 }),
  });

  const photos = data?.photos ?? [];
  const parType = (t: TypePhoto) => photos.find((p) => p.type === t);
  const autres = photos.filter(
    (p) => !OBLIGATOIRES.includes(p.type) || photos.filter((x) => x.type === p.type).indexOf(p) > 0,
  );
  const aGenerer = photos.filter(
    (p) => p.type !== "defaut" && (p.statut === "a_generer" || p.statut === "erreur"),
  ).length;
  // Coût moyen par photo avec les modèles choisis pour chaque type
  const prix = config.data ? config.data.cout_article / 4 : 0.012;

  // Dépôt groupé : les photos remplissent d'abord les emplacements vides (devant, dos, étiquette, logo).
  function deposerEnVrac(fichiers: File[]) {
    const libres = OBLIGATOIRES.filter((t) => !parType(t));
    depot.mutate(fichiers.map((fichier, i) => ({ fichier, type: libres[i] ?? "detail" })));
  }

  return (
    <div className="space-y-3">
      {config.data && (!config.data.configure || !config.data.fond_defini) && (
        <p className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          <AlertCircle className="mt-0.5 size-4 shrink-0" />
          {!config.data.configure ? (
            "La retouche des photos n'est pas configurée sur le serveur (REPLICATE_API_TOKEN)."
          ) : (
            <span>
              Ajoute d&apos;abord la photo de ton tapis :{" "}
              <Link className="underline" href="/parametres?onglet=photos">
                Paramètres → Photos
              </Link>
              .
            </span>
          )}
        </p>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {OBLIGATOIRES.map((t) => {
          const p = parType(t);
          return p ? (
            <CartePhoto key={p.id} photo={p} onChange={rafraichir} />
          ) : (
            <ZoneDepot
              key={t}
              libelle={LIBELLES[t]}
              aide="Déposer la photo"
              className="aspect-[3/4]"
              occupe={depot.isPending}
              onFichiers={(f) => depot.mutate([{ fichier: f[0], type: t }])}
            />
          );
        })}
        {autres.map((p) => (
          <CartePhoto key={p.id} photo={p} onChange={rafraichir} />
        ))}
      </div>

      <div className="grid gap-3 sm:grid-cols-2">
        <ZoneDepot
          multiple
          libelle="Déposer plusieurs photos d'un coup"
          aide="Rangées dans l'ordre : devant, dos, étiquette, logo, puis détails"
          occupe={depot.isPending}
          onFichiers={deposerEnVrac}
        />
        <ZoneDepot
          libelle="Ajouter une photo de défaut"
          aide="Publiée telle quelle, jamais retouchée"
          occupe={depot.isPending}
          onFichiers={(f) => depot.mutate(f.map((fichier) => ({ fichier, type: "defaut" as const })))}
          multiple
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <Button
          className="bg-brand text-brand-foreground hover:bg-brand/90"
          onClick={() => generation.mutate()}
          disabled={!aGenerer || generation.isPending || data?.en_cours || !config.data?.fond_defini}
        >
          {data?.en_cours ? <Loader2 className="animate-spin" /> : <Wand2 />}
          {data?.en_cours
            ? "Retouche en cours…"
            : aGenerer
              ? `Retoucher ${aGenerer} photo${aGenerer > 1 ? "s" : ""}`
              : photos.length
                ? "Tout est retouché"
                : "Retoucher les photos"}
          {aGenerer > 0 && !data?.en_cours && <span className="opacity-80">· ~{dollars(aGenerer * prix)}</span>}
        </Button>
        <Button
          variant="outline"
          disabled={!photos.length}
          onClick={() => telecharger(`/articles/${articleId}/photos.zip`).catch((e) => toast.error(e.message))}
        >
          <Download /> Tout télécharger
        </Button>
        {data && Number(data.cout_total) > 0 && (
          <span className="text-xs text-muted-foreground">Coût de cet article : {dollars(data.cout_total)}</span>
        )}
      </div>
      {data && data.manquantes.length > 0 && photos.length > 0 && (
        <p className="text-xs text-muted-foreground">
          Il manque : {data.manquantes.map((t) => LIBELLES[t].toLowerCase()).join(", ")}.
        </p>
      )}
      <p className="text-xs text-muted-foreground">
        Vérifie toujours la photo retouchée avant de publier : le vêtement doit être exactement le tien (couleur,
        étiquette, logo, usure).
      </p>
    </div>
  );
}
