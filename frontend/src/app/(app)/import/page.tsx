"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Download, FileSpreadsheet, Loader2, Upload, XCircle } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useDropzone } from "react-dropzone";
import { toast } from "sonner";

import { EnTetePage } from "@/components/commun";
import { CelluleEditable } from "@/components/stock/cellule-editable";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { api, telecharger } from "@/lib/api";
import { formatDate, formatEuros } from "@/lib/format";
import { useInvaliderStock } from "@/lib/queries";
import { ORDRE_STATUTS, STATUTS } from "@/lib/statuts";
import type { Anomalie, ApercuImport, LigneImport, Statut } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Recalcule côté client les anomalies corrigeables (le backend revérifie tout à la validation). */
function verifier(l: LigneImport): Anomalie[] {
  const a: Anomalie[] = [];
  if (!l.nom.trim()) a.push({ champ: "nom", niveau: "erreur", message: "Nom manquant" });
  if (l.prix_achat_net === null)
    a.push({ champ: "prix_achat_net", niveau: "erreur", message: "Prix d'achat manquant" });
  if (!l.statut)
    a.push({ champ: "statut", niveau: "erreur", message: `Statut inconnu : « ${l.statut_excel ?? "vide"} »` });
  if (l.statut === "vendu" && l.prix_vente === null)
    a.push({ champ: "prix_vente", niveau: "erreur", message: "Article vendu sans prix de vente" });
  const avertissementStatut = l.anomalies.find((x) => x.champ === "statut" && x.niveau === "avertissement");
  if (avertissementStatut) a.push(avertissementStatut);
  if (!l.taille) a.push({ champ: "taille", niveau: "avertissement", message: "Taille vide" });
  if (!l.marque) a.push({ champ: "marque", niveau: "avertissement", message: "Marque non détectée" });
  if (!l.batch) a.push({ champ: "batch", niveau: "avertissement", message: "Aucun batch" });
  return a;
}

function classeCellule(l: LigneImport, champ: string) {
  const a = l.anomalies.find((x) => x.champ === champ);
  if (!a) return undefined;
  return a.niveau === "erreur"
    ? "bg-red-50 ring-1 ring-inset ring-red-200 dark:bg-red-950/40 dark:ring-red-900"
    : "bg-amber-50 dark:bg-amber-950/30";
}

export default function PageImport() {
  const invalider = useInvaliderStock();
  const [apercu, setApercu] = useState<ApercuImport | null>(null);
  const [problemesSeuls, setProblemesSeuls] = useState(false);
  // Les ventes de l'Excel n'ont pas de date : on les date au hasard dans cette période (modifiable).
  const [daterVentes, setDaterVentes] = useState(true);
  const [ventesDu, setVentesDu] = useState("2026-10-01");
  const [ventesAu, setVentesAu] = useState("2026-10-16");
  const [resultat, setResultat] = useState<{
    articles: number;
    batches: number;
    pistes: number;
    ventes_datees: number;
  } | null>(null);
  const etat = useQuery({
    queryKey: ["import", "etat"],
    queryFn: () => api<{ deja_importe: boolean }>("/import/etat"),
  });

  const lecture = useMutation({
    mutationFn: (fichier: File) => {
      const form = new FormData();
      form.append("fichier", fichier);
      return api<ApercuImport>("/import/excel/preview", { form });
    },
    onSuccess: (a) => {
      setApercu(a);
      setResultat(null);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const validation = useMutation({
    mutationFn: () =>
      api<{ articles: number; batches: number; pistes: number; ventes_datees: number }>("/import/excel/commit", {
        body: {
          lignes: apercu!.lignes,
          pistes: apercu!.pistes,
          periode_ventes: daterVentes ? { du: ventesDu, au: ventesAu } : null,
        },
      }),
    onSuccess: (r) => {
      setResultat(r);
      setApercu(null);
      invalider();
      etat.refetch();
      toast.success("Import terminé");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: { "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"] },
    multiple: false,
    onDrop: (ok, refuses) => {
      if (refuses.length) toast.error("Choisis un fichier Excel (.xlsx).");
      if (ok[0]) lecture.mutate(ok[0]);
    },
  });

  function maj(ligne: number, champs: Partial<LigneImport>) {
    setApercu(
      (a) =>
        a && {
          ...a,
          lignes: a.lignes.map((l) => {
            if (l.ligne !== ligne) return l;
            const n = { ...l, ...champs };
            return { ...n, anomalies: verifier(n) };
          }),
        },
    );
  }

  const stats = useMemo(() => {
    const lignes = apercu?.lignes ?? [];
    return {
      erreurs: lignes.filter((l) => l.anomalies.some((a) => a.niveau === "erreur")).length,
      avertissements: lignes.filter((l) => l.anomalies.length && !l.anomalies.some((a) => a.niveau === "erreur"))
        .length,
      batches: new Set(lignes.map((l) => l.batch).filter(Boolean)).size,
    };
  }, [apercu]);

  const lignesAffichees = (apercu?.lignes ?? []).filter((l) => !problemesSeuls || l.anomalies.length > 0);

  return (
    <>
      <EnTetePage
        titre="Import / export"
        description="Import unique de ton Excel de suivi, puis export à tout moment"
        actions={
          <Button variant="outline" onClick={() => telecharger("/export/excel").catch((e) => toast.error(e.message))}>
            <Download /> Exporter en Excel
          </Button>
        }
      />

      {resultat && (
        <div className="mb-6 flex flex-col gap-3 rounded-xl border border-brand/30 bg-brand-soft/50 p-5 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-start gap-3">
            <CheckCircle2 className="mt-0.5 size-5 text-brand" />
            <div>
              <p className="font-medium">Import terminé : l&apos;app est maintenant ta source de vérité.</p>
              <p className="text-sm text-muted-foreground">
                {resultat.articles} articles, {resultat.batches} batches et {resultat.pistes} pistes de sourcing
                importés.
                {resultat.ventes_datees > 0 && ` ${resultat.ventes_datees} ventes datées au hasard.`}
              </p>
            </div>
          </div>
          <Button asChild>
            <Link href="/stock">Voir le stock</Link>
          </Button>
        </div>
      )}

      {!apercu && (
        <>
          {etat.data?.deja_importe && !resultat && (
            <p className="mb-4 flex items-start gap-2 rounded-lg bg-muted/60 px-3 py-2 text-sm text-muted-foreground">
              <AlertTriangle className="mt-0.5 size-4 shrink-0" />
              L&apos;import a déjà été fait : un nouvel import sera refusé pour ne pas créer de doublons.
            </p>
          )}
          <div
            {...getRootProps()}
            className={cn(
              "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border border-dashed px-6 py-16 text-center transition-colors outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
              isDragActive ? "border-brand bg-brand-soft" : "hover:bg-muted/40",
            )}
          >
            <input {...getInputProps()} aria-label="Fichier Excel à importer" />
            <div className="flex size-12 items-center justify-center rounded-xl border bg-card shadow-sm">
              {lecture.isPending ? (
                <Loader2 className="size-5 animate-spin text-brand" />
              ) : (
                <FileSpreadsheet className="size-5 text-brand" />
              )}
            </div>
            <div>
              <p className="font-medium">
                {lecture.isPending ? "Lecture du fichier…" : "Dépose ton fichier « Suivi revente » (.xlsx)"}
              </p>
              <p className="mt-1 text-sm text-muted-foreground">
                Onglets lus : Suivi revente, Batch 2, Sourcing tests, Sourcing - Recherche. Rien n&apos;est enregistré
                avant ta validation.
              </p>
            </div>
            <Button variant="outline" size="sm" type="button">
              <Upload /> Choisir un fichier
            </Button>
          </div>
        </>
      )}

      {apercu && (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <div className="rounded-xl border bg-card p-4">
              <p className="text-[13px] text-muted-foreground">Articles</p>
              <p className="text-2xl font-semibold tabular-nums">{apercu.lignes.length}</p>
            </div>
            <div className="rounded-xl border bg-card p-4">
              <p className="text-[13px] text-muted-foreground">Batches</p>
              <p className="text-2xl font-semibold tabular-nums">{stats.batches}</p>
            </div>
            <div className="rounded-xl border bg-card p-4">
              <p className="text-[13px] text-muted-foreground">Pistes de sourcing</p>
              <p className="text-2xl font-semibold tabular-nums">{apercu.pistes.length}</p>
            </div>
            <div
              className={cn("rounded-xl border bg-card p-4", stats.erreurs > 0 && "border-red-200 dark:border-red-900")}
            >
              <p className="text-[13px] text-muted-foreground">À corriger</p>
              <p className="text-2xl font-semibold tabular-nums">
                <span className={stats.erreurs ? "text-red-600 dark:text-red-400" : ""}>{stats.erreurs}</span>
                <span className="text-base font-normal text-muted-foreground">
                  {" "}
                  erreurs · {stats.avertissements} avertissements
                </span>
              </p>
            </div>
          </div>

          <div className="flex flex-col gap-3 rounded-xl border bg-card p-4 sm:flex-row sm:items-center">
            <label className="flex items-center gap-2 text-sm">
              <Switch checked={daterVentes} onCheckedChange={setDaterVentes} />
              Dater au hasard les {apercu.lignes.filter((l) => l.statut === "vendu").length} ventes, entre
            </label>
            <div className="flex items-center gap-2">
              <Input
                type="date"
                value={ventesDu}
                onChange={(e) => setVentesDu(e.target.value)}
                disabled={!daterVentes}
                className="h-8 w-40"
                aria-label="Début de la période des ventes"
              />
              <span className="text-sm text-muted-foreground">et</span>
              <Input
                type="date"
                value={ventesAu}
                onChange={(e) => setVentesAu(e.target.value)}
                disabled={!daterVentes}
                className="h-8 w-40"
                aria-label="Fin de la période des ventes"
              />
            </div>
            <p className="text-xs text-muted-foreground sm:ml-auto sm:max-w-56">
              Jamais avant la date d&apos;achat. Sans date, les ventes n&apos;apparaissent dans aucune période de la
              compta.
            </p>
          </div>

          <div className="flex flex-wrap items-center justify-between gap-3">
            <label className="flex items-center gap-2 text-sm">
              <Switch checked={problemesSeuls} onCheckedChange={setProblemesSeuls} />
              Afficher seulement les lignes à vérifier
            </label>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => setApercu(null)}>
                Annuler
              </Button>
              <Button
                onClick={() => validation.mutate()}
                disabled={
                  stats.erreurs > 0 ||
                  validation.isPending ||
                  (daterVentes && (!ventesDu || !ventesAu || ventesDu > ventesAu))
                }
              >
                {validation.isPending && <Loader2 className="animate-spin" />}
                Valider l&apos;import
              </Button>
            </div>
          </div>
          {stats.erreurs > 0 && (
            <p className="text-sm text-red-600 dark:text-red-400">
              Corrige les cellules en rouge pour pouvoir valider.
            </p>
          )}

          <div className="overflow-x-auto rounded-xl border bg-card">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableHead className="w-12">Ligne</TableHead>
                  <TableHead className="w-8" />
                  <TableHead className="min-w-64">Nom</TableHead>
                  <TableHead>Taille</TableHead>
                  <TableHead className="min-w-36">Marque</TableHead>
                  <TableHead className="min-w-28">Catégorie</TableHead>
                  <TableHead className="text-right">Achat net</TableHead>
                  <TableHead className="text-right">Vente</TableHead>
                  <TableHead className="min-w-40">Statut</TableHead>
                  <TableHead>Batch</TableHead>
                  <TableHead>Achat le</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {lignesAffichees.map((l) => {
                  const erreur = l.anomalies.some((a) => a.niveau === "erreur");
                  return (
                    <TableRow key={l.ligne}>
                      <TableCell className="text-muted-foreground tabular-nums">{l.ligne}</TableCell>
                      <TableCell>
                        {l.anomalies.length > 0 && (
                          <Tooltip>
                            <TooltipTrigger aria-label="Problèmes de la ligne">
                              {erreur ? (
                                <XCircle className="size-4 text-red-500" />
                              ) : (
                                <AlertTriangle className="size-4 text-amber-500" />
                              )}
                            </TooltipTrigger>
                            <TooltipContent>
                              <ul>
                                {l.anomalies.map((a, i) => (
                                  <li key={i}>{a.message}</li>
                                ))}
                              </ul>
                            </TooltipContent>
                          </Tooltip>
                        )}
                      </TableCell>
                      <TableCell className={classeCellule(l, "nom")}>
                        <CelluleEditable
                          libelle="le nom"
                          valeur={l.nom}
                          onSave={(v) => maj(l.ligne, { nom: v ?? "" })}
                        />
                      </TableCell>
                      <TableCell className={classeCellule(l, "taille")}>
                        <CelluleEditable
                          libelle="la taille"
                          valeur={l.taille}
                          onSave={(v) => maj(l.ligne, { taille: v })}
                        />
                      </TableCell>
                      <TableCell className={classeCellule(l, "marque")}>
                        <CelluleEditable
                          libelle="la marque"
                          valeur={l.marque}
                          onSave={(v) => maj(l.ligne, { marque: v })}
                        />
                      </TableCell>
                      <TableCell>
                        <CelluleEditable
                          libelle="la catégorie"
                          valeur={l.categorie}
                          onSave={(v) => maj(l.ligne, { categorie: v })}
                        />
                      </TableCell>
                      <TableCell className={cn("w-24", classeCellule(l, "prix_achat_net"))}>
                        <CelluleEditable
                          type="montant"
                          libelle="le prix d'achat"
                          valeur={l.prix_achat_net}
                          affichage={formatEuros(l.prix_achat_net)}
                          onSave={(v) => maj(l.ligne, { prix_achat_net: v })}
                        />
                      </TableCell>
                      <TableCell className={cn("w-24", classeCellule(l, "prix_vente"))}>
                        <CelluleEditable
                          type="montant"
                          libelle="le prix de vente"
                          valeur={l.prix_vente}
                          affichage={formatEuros(l.prix_vente)}
                          onSave={(v) => maj(l.ligne, { prix_vente: v })}
                        />
                      </TableCell>
                      <TableCell className={classeCellule(l, "statut")}>
                        <Select value={l.statut ?? ""} onValueChange={(v) => maj(l.ligne, { statut: v as Statut })}>
                          <SelectTrigger
                            size="sm"
                            className="h-7 w-full border-transparent bg-transparent px-1.5 shadow-none"
                            aria-label="Statut"
                          >
                            <SelectValue placeholder="Choisir…" />
                          </SelectTrigger>
                          <SelectContent>
                            {ORDRE_STATUTS.map((s) => (
                              <SelectItem key={s} value={s}>
                                {STATUTS[s].libelle}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        {l.statut_excel && (
                          <p className="px-1.5 text-[11px] text-muted-foreground">Excel : {l.statut_excel}</p>
                        )}
                      </TableCell>
                      <TableCell className={cn("whitespace-nowrap", classeCellule(l, "batch"))}>
                        <CelluleEditable
                          libelle="le batch"
                          valeur={l.batch}
                          onSave={(v) => maj(l.ligne, { batch: v })}
                        />
                      </TableCell>
                      <TableCell className="text-muted-foreground tabular-nums">{formatDate(l.date_achat)}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </div>
        </div>
      )}
    </>
  );
}
