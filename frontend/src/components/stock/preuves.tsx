"use client";

import { useMutation } from "@tanstack/react-query";
import { Download, Eye, FileText, ImageIcon, Loader2, Trash2, Upload } from "lucide-react";
import { useState } from "react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { TYPES_PREUVE } from "@/lib/statuts";
import type { Preuve } from "@/lib/types";
import { cn } from "@/lib/utils";

const TAILLE_MAX = 15 * 1024 * 1024;
const ACCEPTES = {
  "application/pdf": [".pdf"],
  "image/jpeg": [".jpg", ".jpeg"],
  "image/png": [".png"],
  "image/webp": [".webp"],
  "image/heic": [".heic"],
};

function taille(octets: number) {
  return octets < 1024 * 1024
    ? `${Math.round(octets / 1024)} Ko`
    : `${(octets / 1024 / 1024).toFixed(1).replace(".", ",")} Mo`;
}

export function ZonePreuves({
  cible,
  preuves,
  onChange,
}: {
  cible: { article_id: number } | { batch_id: number };
  preuves: Preuve[];
  onChange: () => void;
}) {
  const [type, setType] = useState("facture");
  const [apercu, setApercu] = useState<Preuve | null>(null);

  const envoi = useMutation({
    mutationFn: async (fichiers: File[]) => {
      for (const fichier of fichiers) {
        const form = new FormData();
        form.append("fichier", fichier);
        form.append("type", type);
        for (const [k, v] of Object.entries(cible)) form.append(k, String(v));
        await api("/preuves", { form });
      }
      return fichiers.length;
    },
    onSuccess: (n) => {
      toast.success(n > 1 ? `${n} preuves ajoutées` : "Preuve ajoutée");
      onChange();
    },
    onError: (e: Error) => {
      toast.error(e.message);
      onChange();
    },
  });

  const suppression = useMutation({
    mutationFn: (id: number) => api(`/preuves/${id}`, { method: "DELETE" }),
    onSuccess: () => {
      toast.success("Preuve supprimée");
      onChange();
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: ACCEPTES,
    maxSize: TAILLE_MAX,
    onDrop: (ok, refuses) => {
      if (refuses.length) toast.error(`${refuses.length} fichier(s) refusé(s) : PDF ou image de 15 Mo maximum.`);
      if (ok.length) envoi.mutate(ok);
    },
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-sm text-muted-foreground">Type</span>
        <Select value={type} onValueChange={setType}>
          <SelectTrigger size="sm" className="w-48" aria-label="Type de preuve">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(TYPES_PREUVE).map(([v, l]) => (
              <SelectItem key={v} value={v}>
                {l}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      <div
        {...getRootProps()}
        className={cn(
          "flex cursor-pointer flex-col items-center justify-center gap-1.5 rounded-xl border border-dashed px-4 py-6 text-center text-sm transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
          isDragActive ? "border-brand bg-brand-soft" : "hover:bg-muted/50",
        )}
      >
        <input {...getInputProps()} aria-label="Ajouter des preuves d'achat" />
        {envoi.isPending ? (
          <Loader2 className="size-5 animate-spin text-muted-foreground" />
        ) : (
          <Upload className="size-5 text-muted-foreground" />
        )}
        <span>
          <span className="font-medium">Glisse tes fichiers ici</span> ou clique pour choisir
        </span>
        <span className="text-xs text-muted-foreground">PDF, JPG, PNG, WEBP, HEIC · 15 Mo max</span>
      </div>

      {preuves.length > 0 && (
        <ul className="divide-y rounded-xl border">
          {preuves.map((p) => {
            const Icone = p.mime === "application/pdf" ? FileText : ImageIcon;
            return (
              <li key={p.id} className="flex items-center gap-3 px-3 py-2">
                <Icone className="size-4 shrink-0 text-muted-foreground" />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{p.nom_original}</p>
                  <p className="text-xs text-muted-foreground">
                    {TYPES_PREUVE[p.type] ?? p.type} · {taille(p.taille_octets)} · {formatDate(p.date_upload)}
                    {p.batch_id && " · preuve du batch"}
                  </p>
                </div>
                {p.mime !== "image/heic" && (
                  <Button variant="ghost" size="icon-sm" aria-label="Aperçu" onClick={() => setApercu(p)}>
                    <Eye />
                  </Button>
                )}
                <Button variant="ghost" size="icon-sm" aria-label="Télécharger" asChild>
                  <a href={`/api/preuves/${p.id}/fichier?telechargement=true`}>
                    <Download />
                  </a>
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Supprimer"
                  onClick={() => {
                    if (confirm(`Supprimer « ${p.nom_original} » ?`)) suppression.mutate(p.id);
                  }}
                >
                  <Trash2 />
                </Button>
              </li>
            );
          })}
        </ul>
      )}

      <Dialog open={!!apercu} onOpenChange={(o) => !o && setApercu(null)}>
        <DialogContent className="sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle className="truncate pr-6">{apercu?.nom_original}</DialogTitle>
          </DialogHeader>
          {apercu &&
            (apercu.mime === "application/pdf" ? (
              <iframe
                title={apercu.nom_original}
                src={`/api/preuves/${apercu.id}/fichier`}
                className="h-[70dvh] w-full rounded-lg border"
              />
            ) : (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={`/api/preuves/${apercu.id}/fichier`}
                alt={apercu.nom_original}
                className="max-h-[70dvh] w-full rounded-lg object-contain"
              />
            ))}
        </DialogContent>
      </Dialog>
    </div>
  );
}
