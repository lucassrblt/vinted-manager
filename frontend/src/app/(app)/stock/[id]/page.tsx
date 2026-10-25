"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Download, Mail, Megaphone, Package, Trash2, Truck } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { IndicateurBadge, LignesSquelette, MessageErreur, StatutBadge } from "@/components/commun";
import { BlocVinted } from "@/components/stock/bloc-vinted";
import { CelluleEditable } from "@/components/stock/cellule-editable";
import { PhotosArticle } from "@/components/photos/photos-article";
import { ZonePreuves } from "@/components/stock/preuves";
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
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api, telecharger } from "@/lib/api";
import { formatCoefficient, formatDate, formatDateHeure, formatDelai, formatEuros, formatPourcent } from "@/lib/format";
import {
  useArticle,
  useBatches,
  useChangerStatut,
  useComptes,
  useInvaliderStock,
  useModifierArticle,
} from "@/lib/queries";
import { ETATS, ORDRE_STATUTS, STATUTS } from "@/lib/statuts";
import type { Article, Historique, LiensArticle } from "@/lib/types";
import { cn } from "@/lib/utils";

function Bloc({
  titre,
  actions,
  children,
  className,
}: {
  titre: string;
  actions?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-xl border bg-card p-4 md:p-5", className)}>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold">{titre}</h2>
        {actions}
      </div>
      {children}
    </section>
  );
}

function Ligne({ libelle, children }: { libelle: string; children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[140px_1fr] items-center gap-2 py-1 text-sm">
      <dt className="text-muted-foreground">{libelle}</dt>
      <dd className="min-w-0">{children}</dd>
    </div>
  );
}

export default function FicheArticle() {
  const id = Number(useParams<{ id: string }>().id);
  const router = useRouter();
  const { data: a, isLoading, error, refetch } = useArticle(id);
  const { data: batches } = useBatches();
  const { data: comptes } = useComptes();
  const timeline = useQuery({
    queryKey: ["timeline", id],
    queryFn: () => api<Historique[]>(`/articles/${id}/timeline`),
  });
  const liens = useQuery({
    queryKey: ["article", id, "liens"],
    queryFn: () => api<LiensArticle>(`/articles/${id}/liens`),
  });
  const modifier = useModifierArticle();
  const changerStatut = useChangerStatut();
  const invalider = useInvaliderStock();
  const [suppression, setSuppression] = useState(false);
  const [notes, setNotes] = useState<string | null>(null);

  if (error) return <MessageErreur erreur={error} reessayer={() => refetch()} />;
  if (isLoading || !a) return <LignesSquelette n={12} />;

  const sauver = (champ: keyof Article | string, v: string | null) =>
    modifier.mutate({ id, [champ]: v }, { onSuccess: () => toast.success("Enregistré") });
  const vendu = ["vendu", "envoye", "livre", "litige"].includes(a.statut);
  const preuves = liens.data?.preuves ?? [];

  async function supprimer() {
    try {
      await api(`/articles/${id}`, { method: "DELETE" });
      invalider();
      toast.success("Article supprimé");
      router.push("/stock");
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <Link
          href="/stock"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" /> Stock
        </Link>
        <div className="mt-2 flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold tracking-tight text-balance">{a.nom}</h1>
            <div className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <DropdownMenu>
                <DropdownMenuTrigger
                  className="rounded-full outline-none focus-visible:ring-2 focus-visible:ring-ring/50"
                  aria-label="Changer le statut"
                >
                  <StatutBadge statut={a.statut} />
                </DropdownMenuTrigger>
                <DropdownMenuContent>
                  {ORDRE_STATUTS.filter((s) => s !== a.statut).map((s) => (
                    <DropdownMenuItem
                      key={s}
                      onClick={() =>
                        changerStatut.mutate(
                          { id, statut: s },
                          { onSuccess: () => toast.success(`Statut : ${STATUTS[s].libelle}`) },
                        )
                      }
                    >
                      <StatutBadge statut={s} />
                    </DropdownMenuItem>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
              {a.marque && <span>{a.marque}</span>}
              {a.taille && <span>· {a.taille}</span>}
              {a.batch_id && (
                <Link href={`/batches/${a.batch_id}`} className="hover:text-foreground hover:underline">
                  · {a.batch_nom}
                </Link>
              )}
            </div>
          </div>
          <div className="flex shrink-0 gap-2">
            <Button variant="outline" asChild>
              <Link href={`/annonces/${a.id}`}>
                <Megaphone /> {a.titre_annonce ? "Voir l'annonce" : "Créer l'annonce"}
              </Link>
            </Button>
            <Button variant="ghost" size="icon" aria-label="Supprimer l'article" onClick={() => setSuppression(true)}>
              <Trash2 />
            </Button>
          </div>
        </div>
      </div>

      {a.statut === "litige" && (
        <div className="flex flex-col gap-3 rounded-xl border border-red-200 bg-red-50 p-4 sm:flex-row sm:items-center sm:justify-between dark:border-red-900/60 dark:bg-red-950/40">
          <div>
            <p className="font-medium text-red-800 dark:text-red-300">Litige en cours</p>
            <p className="text-sm text-red-700/80 dark:text-red-300/80">
              {preuves.length} preuve(s) d&apos;achat disponible(s) pour répondre à Vinted.
            </p>
          </div>
          <Button
            variant="outline"
            disabled={preuves.length === 0}
            onClick={() => telecharger(`/articles/${id}/preuves.zip`).catch((e) => toast.error(e.message))}
          >
            <Download /> Télécharger toutes les preuves
          </Button>
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          { l: "Achat net", v: formatEuros(a.prix_achat_net) },
          { l: vendu ? "Vendu" : "Prix cible", v: formatEuros(a.prix_vente) },
          { l: "Marge", v: formatEuros(a.marge), d: formatPourcent(a.marge_pct) },
          { l: "Coefficient", v: formatCoefficient(a.coefficient), badge: a.indicateur },
        ].map((k) => (
          <div key={k.l} className="rounded-xl border bg-card p-4">
            <p className="text-[13px] text-muted-foreground">{k.l}</p>
            <p className="mt-1 text-xl font-semibold tabular-nums">{k.v}</p>
            {k.d && <p className="text-xs text-muted-foreground">{k.d}</p>}
            {k.badge && (
              <div className="mt-1">
                <IndicateurBadge indicateur={k.badge} />
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="grid gap-5 lg:grid-cols-[1fr_360px]">
        <div className="space-y-5">
          <Bloc titre="Informations">
            <dl className="grid gap-x-8 md:grid-cols-2">
              <div>
                <Ligne libelle="Nom">
                  <CelluleEditable libelle="le nom" valeur={a.nom} onSave={(v) => v && sauver("nom", v)} />
                </Ligne>
                <Ligne libelle="Marque">
                  <CelluleEditable libelle="la marque" valeur={a.marque} onSave={(v) => sauver("marque", v)} />
                </Ligne>
                <Ligne libelle="Catégorie">
                  <CelluleEditable libelle="la catégorie" valeur={a.categorie} onSave={(v) => sauver("categorie", v)} />
                </Ligne>
                <Ligne libelle="Taille">
                  <CelluleEditable libelle="la taille" valeur={a.taille} onSave={(v) => sauver("taille", v)} />
                </Ligne>
                <Ligne libelle="Couleur">
                  <CelluleEditable libelle="la couleur" valeur={a.couleur} onSave={(v) => sauver("couleur", v)} />
                </Ligne>
                <Ligne libelle="État">
                  <Select value={a.etat ?? ""} onValueChange={(v) => sauver("etat", v)}>
                    <SelectTrigger
                      size="sm"
                      className="h-7 w-full border-transparent px-1.5 shadow-none hover:bg-muted"
                      aria-label="État"
                    >
                      <SelectValue placeholder="—" />
                    </SelectTrigger>
                    <SelectContent>
                      {Object.entries(ETATS).map(([v, l]) => (
                        <SelectItem key={v} value={v}>
                          {l}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Ligne>
                <Ligne libelle="Source">
                  <CelluleEditable libelle="la source" valeur={a.source} onSave={(v) => sauver("source", v)} />
                </Ligne>
              </div>
              <div>
                <Ligne libelle="Prix brut">
                  <CelluleEditable
                    type="montant"
                    libelle="le prix brut"
                    valeur={a.prix_achat_brut}
                    affichage={formatEuros(a.prix_achat_brut)}
                    onSave={(v) => sauver("prix_achat_brut", v)}
                    className="text-left"
                  />
                </Ligne>
                <Ligne libelle="Remise">
                  <CelluleEditable
                    type="montant"
                    libelle="la remise"
                    valeur={a.remise}
                    affichage={formatEuros(a.remise)}
                    onSave={(v) => sauver("remise", v ?? "0")}
                    className="text-left"
                  />
                </Ligne>
                <Ligne libelle="Prix net">
                  <span className="px-0 tabular-nums">{formatEuros(a.prix_achat_net)}</span>
                </Ligne>
                <Ligne libelle="Prix cible">
                  <CelluleEditable
                    type="montant"
                    libelle="le prix cible"
                    valeur={a.prix_vente_cible}
                    affichage={formatEuros(a.prix_vente_cible)}
                    onSave={(v) => sauver("prix_vente_cible", v)}
                    className="text-left"
                  />
                </Ligne>
                <Ligne libelle="Prix de vente réel">
                  <CelluleEditable
                    type="montant"
                    libelle="le prix de vente réel"
                    valeur={a.prix_vente_reel}
                    affichage={formatEuros(a.prix_vente_reel)}
                    onSave={(v) => sauver("prix_vente_reel", v)}
                    className="text-left"
                  />
                </Ligne>
                <Ligne libelle="Batch">
                  <Select value={a.batch_id ? String(a.batch_id) : ""} onValueChange={(v) => sauver("batch_id", v)}>
                    <SelectTrigger
                      size="sm"
                      className="h-7 w-full border-transparent px-1.5 shadow-none hover:bg-muted"
                      aria-label="Batch"
                    >
                      <SelectValue placeholder="—" />
                    </SelectTrigger>
                    <SelectContent>
                      {batches?.map((b) => (
                        <SelectItem key={b.id} value={String(b.id)}>
                          {b.nom}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </Ligne>
                {!!comptes?.length && (
                  <Ligne libelle="Compte Vinted">
                    <Select
                      value={a.compte_id ? String(a.compte_id) : "aucun"}
                      onValueChange={(v) => sauver("compte_id", v === "aucun" ? null : v)}
                    >
                      <SelectTrigger
                        size="sm"
                        className="h-7 w-full border-transparent px-1.5 shadow-none hover:bg-muted"
                        aria-label="Compte Vinted"
                      >
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="aucun">Pas encore attribué</SelectItem>
                        {comptes.map((c) => (
                          <SelectItem key={c.id} value={String(c.id)}>
                            {c.nom}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </Ligne>
                )}
                <Ligne libelle="Date d'achat">
                  <span className="tabular-nums">{formatDate(a.date_achat)}</span>
                </Ligne>
              </div>
            </dl>
            <div className="mt-4 space-y-1.5">
              <label htmlFor="notes" className="text-sm text-muted-foreground">
                Notes
              </label>
              <Textarea
                id="notes"
                rows={3}
                value={notes ?? a.notes ?? ""}
                onChange={(e) => setNotes(e.target.value)}
                onBlur={() => {
                  if (notes !== null && notes !== (a.notes ?? "")) sauver("notes", notes || null);
                  setNotes(null);
                }}
              />
            </div>
          </Bloc>

          <Bloc titre="Photos de l'annonce">
            <PhotosArticle articleId={id} />
          </Bloc>

          <Bloc
            titre="Preuves d'achat"
            actions={
              preuves.length > 0 && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => telecharger(`/articles/${id}/preuves.zip`).catch((e) => toast.error(e.message))}
                >
                  <Download /> Tout en zip
                </Button>
              )
            }
          >
            <ZonePreuves cible={{ article_id: id }} preuves={preuves} onChange={() => liens.refetch()} />
          </Bloc>
        </div>

        <div className="space-y-5">
          <Bloc titre="Vinted">
            <BlocVinted article={a} />
          </Bloc>
          <Bloc titre="Historique">
            {timeline.data && timeline.data.length > 0 ? (
              <ol className="relative space-y-4 border-l pl-5">
                {timeline.data.map((h) => (
                  <li key={h.id} className="relative">
                    <span
                      aria-hidden
                      className={cn(
                        "absolute top-1.5 -left-[25px] size-2.5 rounded-full ring-4 ring-card",
                        STATUTS[h.nouveau_statut]?.point,
                      )}
                    />
                    <StatutBadge statut={h.nouveau_statut} />
                    <p className="mt-1 text-xs text-muted-foreground tabular-nums">
                      {formatDateHeure(h.date)}
                      {h.commentaire && ` · ${h.commentaire}`}
                    </p>
                  </li>
                ))}
              </ol>
            ) : (
              <p className="text-sm text-muted-foreground">Aucun changement de statut.</p>
            )}
            {(a.date_publication || a.date_vente) && (
              <dl className="mt-4 border-t pt-3">
                <Ligne libelle="Publié le">{formatDateHeure(a.date_publication)}</Ligne>
                <Ligne libelle="Vendu le">{formatDateHeure(a.date_vente)}</Ligne>
                <Ligne libelle="Délai de vente">{formatDelai(a.delai_vente_heures)}</Ligne>
              </dl>
            )}
          </Bloc>

          <Bloc titre="Ventes et envois">
            {liens.data && (liens.data.ventes.length > 0 || liens.data.envois.length > 0) ? (
              <ul className="space-y-2 text-sm">
                {liens.data.ventes.map((v) => (
                  <li key={v.id} className="flex items-center gap-2">
                    <Package className="size-4 text-muted-foreground" />
                    {formatEuros(v.prix)} · {formatDateHeure(v.date_heure)}
                    {v.acheteur && <span className="text-muted-foreground">· {v.acheteur}</span>}
                  </li>
                ))}
                {liens.data.envois.map((e) => (
                  <li key={e.id} className="flex items-center gap-2">
                    <Truck className="size-4 text-muted-foreground" /> Envoi {e.statut.replace("_", " ")}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">
                Les ventes détectées dans tes mails apparaîtront ici (étape 2).
              </p>
            )}
          </Bloc>

          <Bloc titre="Mails liés">
            {liens.data && liens.data.mails.length > 0 ? (
              <ul className="space-y-2 text-sm">
                {liens.data.mails.map((m) => (
                  <li key={m.id} className="flex items-start gap-2">
                    <Mail className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                    <span className="min-w-0">
                      <span className="block truncate">{m.sujet}</span>
                      <span className="text-xs text-muted-foreground">{formatDateHeure(m.date)}</span>
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">Aucun mail lié pour l&apos;instant.</p>
            )}
          </Bloc>
        </div>
      </div>

      <AlertDialog open={suppression} onOpenChange={setSuppression}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Supprimer cet article ?</AlertDialogTitle>
            <AlertDialogDescription>
              Ses preuves d&apos;achat et son historique seront supprimés. Action définitive.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Annuler</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={supprimer}>
              Supprimer
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
