"use client";

import {
  ArrowDown,
  ArrowUp,
  ArrowUpDown,
  Boxes,
  ChevronLeft,
  ChevronRight,
  Layers,
  Plus,
  Search,
  Trash2,
  X,
} from "lucide-react";
import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { toast } from "sonner";

import {
  EnTetePage,
  EtatVide,
  IndicateurBadge,
  LignesSquelette,
  MessageErreur,
  StatutBadge,
} from "@/components/commun";
import { CelluleEditable } from "@/components/stock/cellule-editable";
import { DialogArticle } from "@/components/stock/dialog-article";
import { DialogBatch } from "@/components/stock/dialog-batch";
import { FiltreMulti } from "@/components/stock/filtre-multi";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSub,
  DropdownMenuSubContent,
  DropdownMenuSubTrigger,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useDebounce } from "@/hooks/use-debounce";
import { formatCoefficient, formatEuros } from "@/lib/format";
import {
  type FiltresStock,
  useActionGroupee,
  useArticles,
  useBatches,
  useChangerStatut,
  useModifierArticle,
  useValeursFiltres,
} from "@/lib/queries";
import { ORDRE_STATUTS, STATUTS } from "@/lib/statuts";
import type { Article, Statut } from "@/lib/types";
import { cn } from "@/lib/utils";

const TAILLE_PAGE = 50;

function EnTeteTri({
  libelle,
  cle,
  filtres,
  setTri,
  className,
}: {
  libelle: string;
  cle: string;
  filtres: FiltresStock;
  setTri: (cle: string) => void;
  className?: string;
}) {
  const actif = filtres.tri === cle;
  const Icone = !actif ? ArrowUpDown : filtres.ordre === "asc" ? ArrowUp : ArrowDown;
  return (
    <TableHead
      className={className}
      aria-sort={actif ? (filtres.ordre === "asc" ? "ascending" : "descending") : "none"}
    >
      <button
        type="button"
        onClick={() => setTri(cle)}
        className={cn(
          "-mx-1 inline-flex items-center gap-1 rounded px-1 outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/50",
          actif && "text-foreground",
        )}
      >
        {libelle}
        <Icone className={cn("size-3", !actif && "opacity-40")} />
      </button>
    </TableHead>
  );
}

export default function PageStock() {
  return (
    <Suspense fallback={<LignesSquelette n={10} />}>
      <ContenuStock />
    </Suspense>
  );
}

function ContenuStock() {
  // Filtre de statut initial depuis l'URL (liens de l'écran du jour : /stock?statut=litige)
  const statutUrl = useSearchParams()
    .getAll("statut")
    .filter((s): s is Statut => s in STATUTS);
  const [filtres, setFiltres] = useState<FiltresStock>({
    tri: "created_at",
    ordre: "desc",
    page: 1,
    statut: statutUrl.length ? statutUrl : undefined,
  });
  const [recherche, setRecherche] = useState("");
  const q = useDebounce(recherche, 250);
  const [selection, setSelection] = useState<Set<number>>(new Set());
  const [dialogArticle, setDialogArticle] = useState(false);
  const [dialogBatch, setDialogBatch] = useState(false);
  const [confirmSuppr, setConfirmSuppr] = useState(false);

  const requete = { ...filtres, q: q || undefined, taille_page: TAILLE_PAGE };
  const { data, isLoading, isFetching, error, refetch } = useArticles(requete);
  const { data: valeurs } = useValeursFiltres();
  const { data: batches } = useBatches();
  const modifier = useModifierArticle();
  const changerStatut = useChangerStatut();
  const action = useActionGroupee();

  const articles = data?.items ?? [];
  const nbPages = data ? Math.max(1, Math.ceil(data.total / TAILLE_PAGE)) : 1;
  const filtresActifs =
    !!q || [filtres.statut, filtres.batch_id, filtres.marque, filtres.categorie, filtres.taille].some((f) => f?.length);

  function majFiltre<K extends keyof FiltresStock>(cle: K, v: FiltresStock[K]) {
    setFiltres((f) => ({ ...f, [cle]: v, page: 1 }));
    setSelection(new Set());
  }

  function setTri(cle: string) {
    setFiltres((f) => ({
      ...f,
      tri: cle,
      ordre: f.tri === cle && f.ordre === "desc" ? "asc" : "desc",
      page: 1,
    }));
  }

  function basculer(id: number) {
    setSelection((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }

  const toutSelectionne = articles.length > 0 && articles.every((a) => selection.has(a.id));

  function groupe(corps: { action: string; statut?: Statut; batch_id?: number | null }, message: string) {
    action.mutate(
      { ids: [...selection], ...corps },
      {
        onSuccess: (r) => {
          toast.success(`${r.modifies} article(s) ${message}`);
          setSelection(new Set());
        },
      },
    );
  }

  function sauver(a: Article, champ: string, valeur: string | null) {
    modifier.mutate({ id: a.id, [champ]: valeur }, { onSuccess: () => toast.success("Modification enregistrée") });
  }

  return (
    <>
      <EnTetePage
        titre="Stock"
        description={data ? `${data.total} article${data.total > 1 ? "s" : ""}` : " "}
        actions={
          <>
            <Button variant="outline" onClick={() => setDialogBatch(true)}>
              <Layers /> Ajouter un batch
            </Button>
            <Button onClick={() => setDialogArticle(true)}>
              <Plus /> Ajouter un article
            </Button>
          </>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative w-full sm:w-64">
          <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={recherche}
            onChange={(e) => {
              setRecherche(e.target.value);
              setFiltres((f) => ({ ...f, page: 1 }));
            }}
            placeholder="Rechercher un article…"
            aria-label="Rechercher un article"
            className="h-8 pl-8"
          />
        </div>
        <FiltreMulti
          titre="Statut"
          options={ORDRE_STATUTS.map((s) => ({ valeur: s, libelle: STATUTS[s].libelle }))}
          selection={filtres.statut ?? []}
          onChange={(v) => majFiltre("statut", v)}
        />
        <FiltreMulti
          titre="Batch"
          options={(batches ?? []).map((b) => ({ valeur: b.id, libelle: b.nom }))}
          selection={filtres.batch_id ?? []}
          onChange={(v) => majFiltre("batch_id", v)}
        />
        <FiltreMulti
          titre="Marque"
          options={(valeurs?.marques ?? []).map((m) => ({ valeur: m, libelle: m }))}
          selection={filtres.marque ?? []}
          onChange={(v) => majFiltre("marque", v)}
        />
        <FiltreMulti
          titre="Catégorie"
          options={(valeurs?.categories ?? []).map((m) => ({ valeur: m, libelle: m }))}
          selection={filtres.categorie ?? []}
          onChange={(v) => majFiltre("categorie", v)}
        />
        <FiltreMulti
          titre="Taille"
          options={(valeurs?.tailles ?? []).map((m) => ({ valeur: m, libelle: m }))}
          selection={filtres.taille ?? []}
          onChange={(v) => majFiltre("taille", v)}
        />
        {filtresActifs && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setRecherche("");
              setFiltres({ tri: filtres.tri, ordre: filtres.ordre, page: 1 });
            }}
          >
            <X /> Réinitialiser
          </Button>
        )}
      </div>

      {selection.size > 0 && (
        <div className="sticky top-16 z-20 mb-3 flex animate-in flex-wrap items-center gap-2 rounded-xl border bg-card/95 px-3 py-2 shadow-sm backdrop-blur fade-in slide-in-from-top-1">
          <span className="text-sm font-medium tabular-nums">{selection.size} sélectionné(s)</span>
          <div className="ml-auto flex flex-wrap gap-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => groupe({ action: "publie_aujourdhui" }, "publié(s) aujourd'hui")}
            >
              Publié aujourd&apos;hui
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm" variant="outline">
                  Changer le statut
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                {ORDRE_STATUTS.map((s) => (
                  <DropdownMenuItem key={s} onClick={() => groupe({ action: "statut", statut: s }, "mis à jour")}>
                    <StatutBadge statut={s} />
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button size="sm" variant="outline">
                  Affecter à un batch
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent>
                <DropdownMenuItem onClick={() => groupe({ action: "batch", batch_id: null }, "retiré(s) du batch")}>
                  Aucun batch
                </DropdownMenuItem>
                {batches?.map((b) => (
                  <DropdownMenuItem
                    key={b.id}
                    onClick={() => groupe({ action: "batch", batch_id: b.id }, `affecté(s) à ${b.nom}`)}
                  >
                    {b.nom}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
            <Button size="sm" variant="destructive" onClick={() => setConfirmSuppr(true)}>
              <Trash2 /> Supprimer
            </Button>
            <Button size="sm" variant="ghost" onClick={() => setSelection(new Set())} aria-label="Annuler la sélection">
              <X />
            </Button>
          </div>
        </div>
      )}

      {error ? (
        <MessageErreur erreur={error} reessayer={() => refetch()} />
      ) : isLoading ? (
        <LignesSquelette n={10} />
      ) : articles.length === 0 ? (
        filtresActifs ? (
          <EtatVide icone={Search} titre="Aucun article ne correspond" texte="Modifie la recherche ou les filtres." />
        ) : (
          <EtatVide
            icone={Boxes}
            titre="Ton stock est vide"
            texte="Importe ton Excel de suivi ou ajoute un premier article."
            action={{ libelle: "Importer l'Excel", href: "/import" }}
          />
        )
      ) : (
        <>
          {/* Vue mobile : cartes */}
          <ul className={cn("space-y-2 md:hidden", isFetching && "opacity-70")}>
            {articles.map((a) => (
              <li key={a.id}>
                <Link href={`/stock/${a.id}`} className="block rounded-xl border bg-card p-3 active:bg-muted">
                  <div className="flex items-start justify-between gap-2">
                    <span className="leading-snug font-medium">{a.nom}</span>
                    <StatutBadge statut={a.statut} />
                  </div>
                  <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted-foreground tabular-nums">
                    {a.taille && <span>{a.taille}</span>}
                    <span>Achat {formatEuros(a.prix_achat_net)}</span>
                    <span>Vente {formatEuros(a.prix_vente)}</span>
                    <IndicateurBadge indicateur={a.indicateur} />
                  </div>
                </Link>
              </li>
            ))}
          </ul>

          {/* Vue bureau : tableau */}
          <div className={cn("hidden overflow-x-auto rounded-xl border bg-card md:block", isFetching && "opacity-80")}>
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableHead className="w-9">
                    <Checkbox
                      aria-label="Tout sélectionner"
                      checked={toutSelectionne}
                      onCheckedChange={(v) => setSelection(v ? new Set(articles.map((a) => a.id)) : new Set())}
                    />
                  </TableHead>
                  <EnTeteTri libelle="Article" cle="nom" filtres={filtres} setTri={setTri} className="min-w-64" />
                  <EnTeteTri libelle="Taille" cle="taille" filtres={filtres} setTri={setTri} />
                  <EnTeteTri
                    libelle="Achat net"
                    cle="prix_achat_net"
                    filtres={filtres}
                    setTri={setTri}
                    className="text-right"
                  />
                  <EnTeteTri
                    libelle="Vente"
                    cle="prix_vente"
                    filtres={filtres}
                    setTri={setTri}
                    className="text-right"
                  />
                  <EnTeteTri libelle="Marge" cle="marge" filtres={filtres} setTri={setTri} className="text-right" />
                  <EnTeteTri libelle="Coeff." cle="coefficient" filtres={filtres} setTri={setTri} />
                  <EnTeteTri libelle="Statut" cle="statut" filtres={filtres} setTri={setTri} />
                  <TableHead>Batch</TableHead>
                  <EnTeteTri
                    libelle="En ligne"
                    cle="date_publication"
                    filtres={filtres}
                    setTri={setTri}
                    className="text-right"
                  />
                </TableRow>
              </TableHeader>
              <TableBody>
                {articles.map((a) => (
                  <TableRow key={a.id} data-state={selection.has(a.id) ? "selected" : undefined}>
                    <TableCell>
                      <Checkbox
                        aria-label={`Sélectionner ${a.nom}`}
                        checked={selection.has(a.id)}
                        onCheckedChange={() => basculer(a.id)}
                      />
                    </TableCell>
                    <TableCell className="max-w-80">
                      <Link
                        href={`/stock/${a.id}`}
                        className="block truncate font-medium outline-none hover:underline focus-visible:underline"
                      >
                        {a.nom}
                      </Link>
                      {a.marque && <span className="text-xs text-muted-foreground">{a.marque}</span>}
                    </TableCell>
                    <TableCell className="w-20">
                      <CelluleEditable libelle="la taille" valeur={a.taille} onSave={(v) => sauver(a, "taille", v)} />
                    </TableCell>
                    <TableCell className="w-28 text-right tabular-nums">
                      <CelluleEditable
                        type="montant"
                        libelle="le prix d'achat net"
                        valeur={a.prix_achat_net}
                        affichage={formatEuros(a.prix_achat_net)}
                        onSave={(v) => sauver(a, "prix_achat_net", v)}
                      />
                    </TableCell>
                    <TableCell className="w-28 text-right tabular-nums">
                      <CelluleEditable
                        type="montant"
                        libelle="le prix de vente"
                        valeur={a.prix_vente}
                        affichage={formatEuros(a.prix_vente)}
                        onSave={(v) =>
                          sauver(
                            a,
                            ["vendu", "envoye", "livre", "litige"].includes(a.statut)
                              ? "prix_vente_reel"
                              : "prix_vente_cible",
                            v,
                          )
                        }
                      />
                    </TableCell>
                    <TableCell
                      className={cn(
                        "text-right tabular-nums",
                        a.marge !== null && Number(a.marge) < 0 && "text-red-600 dark:text-red-400",
                      )}
                    >
                      {formatEuros(a.marge)}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5">
                        <span className="w-11 tabular-nums">{formatCoefficient(a.coefficient)}</span>
                        <IndicateurBadge indicateur={a.indicateur} />
                      </div>
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger
                          className="rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                          aria-label={`Statut : ${STATUTS[a.statut].libelle}`}
                        >
                          <StatutBadge statut={a.statut} />
                        </DropdownMenuTrigger>
                        <DropdownMenuContent>
                          {ORDRE_STATUTS.filter((s) => s !== a.statut).map((s) => (
                            <DropdownMenuItem
                              key={s}
                              onClick={() =>
                                changerStatut.mutate(
                                  { id: a.id, statut: s },
                                  { onSuccess: () => toast.success(`Statut : ${STATUTS[s].libelle}`) },
                                )
                              }
                            >
                              <StatutBadge statut={s} />
                            </DropdownMenuItem>
                          ))}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      <DropdownMenu>
                        <DropdownMenuTrigger className="max-w-32 truncate rounded px-1 outline-none hover:bg-muted focus-visible:ring-2 focus-visible:ring-ring/50">
                          {a.batch_nom ?? "—"}
                        </DropdownMenuTrigger>
                        <DropdownMenuContent>
                          <DropdownMenuSub>
                            <DropdownMenuSubTrigger>Changer de batch</DropdownMenuSubTrigger>
                            <DropdownMenuSubContent>
                              {batches?.map((b) => (
                                <DropdownMenuItem key={b.id} onClick={() => sauver(a, "batch_id", String(b.id))}>
                                  {b.nom}
                                </DropdownMenuItem>
                              ))}
                            </DropdownMenuSubContent>
                          </DropdownMenuSub>
                          {a.batch_id && (
                            <DropdownMenuItem asChild>
                              <Link href={`/batches/${a.batch_id}`}>Voir le batch</Link>
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                    <TableCell className="text-right text-muted-foreground tabular-nums">
                      {a.jours_en_ligne !== null ? `${a.jours_en_ligne} j` : "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {nbPages > 1 && (
            <div className="mt-4 flex items-center justify-end gap-2 text-sm">
              <span className="text-muted-foreground tabular-nums">
                Page {filtres.page} sur {nbPages}
              </span>
              <Button
                variant="outline"
                size="icon-sm"
                aria-label="Page précédente"
                disabled={(filtres.page ?? 1) <= 1}
                onClick={() => setFiltres((f) => ({ ...f, page: (f.page ?? 1) - 1 }))}
              >
                <ChevronLeft />
              </Button>
              <Button
                variant="outline"
                size="icon-sm"
                aria-label="Page suivante"
                disabled={(filtres.page ?? 1) >= nbPages}
                onClick={() => setFiltres((f) => ({ ...f, page: (f.page ?? 1) + 1 }))}
              >
                <ChevronRight />
              </Button>
            </div>
          )}
        </>
      )}

      <DialogArticle ouvert={dialogArticle} setOuvert={setDialogArticle} />
      <DialogBatch ouvert={dialogBatch} setOuvert={setDialogBatch} />
      <AlertDialog open={confirmSuppr} onOpenChange={setConfirmSuppr}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Supprimer {selection.size} article(s) ?</AlertDialogTitle>
            <AlertDialogDescription>
              Leurs preuves d&apos;achat et leur historique seront supprimés aussi. Cette action est définitive.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={() => groupe({ action: "supprimer" }, "supprimé(s)")}>
              Supprimer
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}
