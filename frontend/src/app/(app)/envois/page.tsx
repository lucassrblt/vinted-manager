"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Download, ExternalLink, FileText, Link2, Loader2, PackageCheck, Printer, Truck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { EnTetePage, EtatVide, LignesSquelette, MessageErreur } from "@/components/commun";
import { SelecteurArticle } from "@/components/selecteur-article";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api, telecharger } from "@/lib/api";
import { echeance, formatDate, formatDateHeure, formatEuros } from "@/lib/format";
import { useInvaliderStock } from "@/lib/queries";
import { STATUTS_ENVOI } from "@/lib/statuts";
import type { DonneesExtraites, EnvoiListe, StatutEnvoi } from "@/lib/types";
import { cn } from "@/lib/utils";

interface ReponseEnvois {
  envois: EnvoiListe[];
  bordereaux_a_rattacher: { email_id: number; date: string | null; sujet: string | null; donnees: DonneesExtraites }[];
}

const ETAPE_SUIVANTE: Partial<Record<StatutEnvoi, { statut: StatutEnvoi; libelle: string; icone: typeof Printer }>> = {
  a_imprimer: { statut: "imprime", libelle: "Imprimé", icone: Printer },
  imprime: { statut: "depose", libelle: "Déposé", icone: Truck },
  depose: { statut: "livre", libelle: "Livré", icone: PackageCheck },
};

function BadgeEcheance({ date, statut }: { date: string | null; statut: StatutEnvoi }) {
  if (statut === "depose" || statut === "livre") return null;
  const e = echeance(date);
  if (!e) return null;
  const styles = {
    retard: "bg-red-600 text-white",
    aujourdhui: "bg-amber-500 text-white",
    demain: "bg-amber-100 text-amber-900 dark:bg-amber-950 dark:text-amber-200",
    plus_tard: "bg-muted text-muted-foreground",
  };
  const textes = {
    retard: "En retard",
    aujourdhui: "Aujourd'hui",
    demain: "Demain",
    plus_tard: `Avant le ${formatDate(date)}`,
  };
  return (
    <span className={cn("inline-flex h-5 items-center rounded-full px-2 text-xs font-semibold", styles[e])}>
      {textes[e]}
    </span>
  );
}

export default function PageEnvois() {
  const qc = useQueryClient();
  const invaliderStock = useInvaliderStock();
  const [termines, setTermines] = useState(false);
  const [selection, setSelection] = useState<Set<number>>(new Set());
  const [format10x15, setFormat10x15] = useState(false);
  const [telechargement, setTelechargement] = useState(false);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["envois", termines],
    queryFn: () => api<ReponseEnvois>("/envois", { params: { termines } }),
    refetchInterval: 60_000,
  });
  const invalider = () => {
    qc.invalidateQueries({ queryKey: ["envois"] });
    invaliderStock();
  };

  const avancer = useMutation({
    mutationFn: ({ id, statut }: { id: number; statut: StatutEnvoi }) =>
      api<EnvoiListe>(`/envois/${id}`, { method: "PATCH", body: { statut } }),
    onSuccess: (e) => {
      invalider();
      toast.success(`${e.article.nom} : ${STATUTS_ENVOI[e.statut].libelle.toLowerCase()}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const rattacher = useMutation({
    mutationFn: ({ emailId, articleId }: { emailId: number; articleId: number }) =>
      api(`/emails/${emailId}/rattacher`, { body: { article_id: articleId } }),
    onSuccess: () => {
      invalider();
      toast.success("Bordereau rattaché");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  const envois = data?.envois ?? [];
  const avecPdf = envois.filter((e) => e.a_bordereau_pdf && e.statut === "a_imprimer");
  const cibles = selection.size ? envois.filter((e) => selection.has(e.id) && e.a_bordereau_pdf) : avecPdf;

  async function telechargerTout() {
    if (!cibles.length) return;
    setTelechargement(true);
    try {
      await telecharger("/envois/bordereaux.pdf", {
        ids: cibles.map((e) => e.id),
        format: format10x15 ? "10x15" : "a4",
        marquer_imprimes: true,
      });
      toast.success(`${cibles.length} bordereau(x) téléchargé(s) et marqué(s) imprimé(s)`);
      setSelection(new Set());
      invalider();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setTelechargement(false);
    }
  }

  return (
    <>
      <EnTetePage
        titre="Envois"
        description="Colis à préparer, triés par date limite"
        actions={
          !termines && (
            <div className="flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-2 text-sm">
                <Switch checked={format10x15} onCheckedChange={setFormat10x15} />
                Format 10x15
              </label>
              <Button onClick={telechargerTout} disabled={!cibles.length || telechargement}>
                {telechargement ? <Loader2 className="animate-spin" /> : <Download />}
                {selection.size
                  ? `Télécharger la sélection (${cibles.length})`
                  : `Télécharger tous les bordereaux (${cibles.length})`}
              </Button>
            </div>
          )
        }
      />

      <Tabs
        value={termines ? "termines" : "en_cours"}
        onValueChange={(v) => setTermines(v === "termines")}
        className="mb-4"
      >
        <TabsList>
          <TabsTrigger value="en_cours">À traiter</TabsTrigger>
          <TabsTrigger value="termines">Livrés</TabsTrigger>
        </TabsList>
      </Tabs>

      {data && data.bordereaux_a_rattacher.length > 0 && !termines && (
        <section className="mb-5 rounded-xl border border-amber-200 bg-amber-50/60 p-4 dark:border-amber-900/60 dark:bg-amber-950/30">
          <h2 className="text-sm font-semibold">Bordereaux à rattacher</h2>
          <p className="mb-3 text-xs text-muted-foreground">
            Ces bordereaux n&apos;ont pas pu être associés automatiquement à une vente : choisis l&apos;article vendu.
          </p>
          <ul className="space-y-2">
            {data.bordereaux_a_rattacher.map((b) => (
              <li
                key={b.email_id}
                className="flex flex-col gap-2 rounded-lg border bg-card p-3 sm:flex-row sm:items-center"
              >
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium">{b.sujet}</p>
                  <p className="text-xs text-muted-foreground">
                    {formatDateHeure(b.date)}
                    {b.donnees.titre_article && ` · « ${b.donnees.titre_article} »`}
                  </p>
                </div>
                <SelecteurArticle
                  libelle="Article vendu…"
                  statuts={["vendu"]}
                  desactive={rattacher.isPending}
                  onChoix={(a) => rattacher.mutate({ emailId: b.email_id, articleId: a.id })}
                />
              </li>
            ))}
          </ul>
        </section>
      )}

      {error ? (
        <MessageErreur erreur={error} reessayer={() => refetch()} />
      ) : isLoading ? (
        <LignesSquelette n={5} />
      ) : envois.length === 0 ? (
        <EtatVide
          icone={Truck}
          titre={termines ? "Aucun colis livré pour l'instant" : "Aucun colis à préparer"}
          texte={termines ? undefined : "Les ventes détectées dans tes mails créent automatiquement un envoi ici."}
          action={termines ? undefined : { libelle: "Voir les ventes", href: "/ventes" }}
        />
      ) : (
        <ul className="space-y-2">
          {envois.map((e) => {
            const suite = ETAPE_SUIVANTE[e.statut];
            const retard = echeance(e.date_limite_envoi) === "retard" && ["a_imprimer", "imprime"].includes(e.statut);
            return (
              <li
                key={e.id}
                className={cn(
                  "flex gap-3 rounded-xl border bg-card p-3 md:items-center md:p-4",
                  retard && "border-red-300 dark:border-red-900",
                )}
              >
                {!termines && (
                  <Checkbox
                    className="mt-1 md:mt-0"
                    aria-label={`Sélectionner ${e.article.nom}`}
                    checked={selection.has(e.id)}
                    onCheckedChange={() =>
                      setSelection((s) => {
                        const n = new Set(s);
                        if (n.has(e.id)) n.delete(e.id);
                        else n.add(e.id);
                        return n;
                      })
                    }
                  />
                )}
                <div className="flex min-w-0 flex-1 flex-col gap-3 md:flex-row md:items-center">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <BadgeEcheance date={e.date_limite_envoi} statut={e.statut} />
                      <span
                        className={cn("rounded-full px-2 py-0.5 text-xs font-medium", STATUTS_ENVOI[e.statut].classe)}
                      >
                        {STATUTS_ENVOI[e.statut].libelle}
                      </span>
                    </div>
                    <Link href={`/stock/${e.article.id}`} className="mt-1.5 block truncate font-medium hover:underline">
                      {e.article.nom}
                    </Link>
                    <p className="text-sm text-muted-foreground tabular-nums">
                      {[
                        e.article.taille,
                        formatEuros(e.vente.prix),
                        e.vente.acheteur && `pour ${e.vente.acheteur}`,
                        `vendu le ${formatDate(e.vente.date_heure)}`,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    {e.a_bordereau_pdf ? (
                      <Button variant="outline" size="sm" asChild>
                        <a href={`/api/envois/${e.id}/bordereau`} target="_blank" rel="noreferrer">
                          <FileText /> Bordereau
                        </a>
                      </Button>
                    ) : e.lien_bordereau ? (
                      <Button variant="outline" size="sm" asChild>
                        <a href={e.lien_bordereau} target="_blank" rel="noreferrer noopener">
                          <ExternalLink /> Lien du bordereau
                        </a>
                      </Button>
                    ) : (
                      <span className="flex items-center gap-1 text-xs text-muted-foreground">
                        <Link2 className="size-3.5" /> Bordereau pas encore reçu
                      </span>
                    )}
                    {suite && (
                      <Button
                        size="sm"
                        onClick={() => avancer.mutate({ id: e.id, statut: suite.statut })}
                        disabled={avancer.isPending}
                      >
                        <suite.icone /> {suite.libelle}
                      </Button>
                    )}
                    {e.statut === "livre" && (
                      <span className="flex items-center gap-1 text-sm text-brand">
                        <Check className="size-4" /> Livré
                      </span>
                    )}
                  </div>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </>
  );
}
