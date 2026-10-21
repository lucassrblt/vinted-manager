"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Inbox, Loader2, Paperclip, Wand2, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { EnTetePage, EtatVide, LignesSquelette, MessageErreur } from "@/components/commun";
import { BadgeCompte } from "@/components/badge-compte";
import { BoutonSynchro } from "@/components/mails/bouton-synchro";
import { type BrouillonRegle, EditeurRegle, REGLE_VIDE } from "@/components/mails/editeur-regle";
import { SelecteurArticle } from "@/components/selecteur-article";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";
import { formatDateHeure } from "@/lib/format";
import { useComptes, useInvaliderStock } from "@/lib/queries";
import { TYPES_EMAIL } from "@/lib/statuts";
import type { EmailDetail, EmailResume, StatutTraitement, TypeEmail } from "@/lib/types";
import { cn } from "@/lib/utils";

type Onglet = "a_classer" | "a_rattacher" | "tous";

const FILTRES: Record<Onglet, { statut?: StatutTraitement[]; type?: TypeEmail[] }> = {
  a_classer: { statut: ["a_classer"] },
  // Type reconnu mais action en attente ; les ventes ont leur propre page.
  a_rattacher: { statut: ["nouveau"], type: ["bordereau", "expedie", "livre", "litige", "message", "offre"] },
  tous: {},
};

const LIBELLES_STATUT: Record<StatutTraitement, string> = {
  nouveau: "En attente",
  traite: "Traité",
  ignore: "Ignoré",
  a_classer: "Non classé",
};

function DetailMail({ id, fermer }: { id: number; fermer: () => void }) {
  const qc = useQueryClient();
  const invaliderStock = useInvaliderStock();
  const [regle, setRegle] = useState<BrouillonRegle | null>(null);
  const { data: m } = useQuery({ queryKey: ["email", id], queryFn: () => api<EmailDetail>(`/emails/${id}`) });
  const invalider = () => {
    qc.invalidateQueries({ queryKey: ["emails"] });
    qc.invalidateQueries({ queryKey: ["email", id] });
    invaliderStock();
  };

  const classer = useMutation({
    mutationFn: (type: TypeEmail | null) => api<EmailDetail>(`/emails/${id}/classer`, { body: { type } }),
    onSuccess: (r) => {
      invalider();
      toast.success(r.statut_traitement === "ignore" ? "Mail ignoré" : `Classé : ${TYPES_EMAIL[r.type_detecte!]}`);
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const rattacher = useMutation({
    mutationFn: (articleId: number) => api(`/emails/${id}/rattacher`, { body: { article_id: articleId } }),
    onSuccess: () => {
      invalider();
      toast.success("Mail rattaché à l'article");
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const suggestion = useMutation({
    mutationFn: () =>
      api<Omit<BrouillonRegle, "active"> & { apercu: Record<string, string> }>(`/emails/${id}/suggestion-regle`, {
        method: "POST",
      }),
    onSuccess: (s) =>
      setRegle({
        ...REGLE_VIDE,
        nom: s.nom,
        type_cible: s.type_cible ?? "autre",
        priorite: s.priorite,
        conditions: s.conditions,
        extraction: s.extraction,
      }),
    onError: (e: Error) => toast.error(e.message),
  });

  if (!m) return <LignesSquelette n={6} />;
  const donnees = Object.entries(m.donnees_extraites);

  return (
    <div className="space-y-5">
      <dl className="grid grid-cols-[110px_1fr] gap-x-3 gap-y-1.5 text-sm">
        <dt className="text-muted-foreground">De</dt>
        <dd className="truncate">{m.expediteur}</dd>
        {m.compte && (
          <>
            <dt className="text-muted-foreground">Compte</dt>
            <dd>{m.compte}</dd>
          </>
        )}
        <dt className="text-muted-foreground">Reçu le</dt>
        <dd>{formatDateHeure(m.date)}</dd>
        <dt className="text-muted-foreground">Type</dt>
        <dd>
          {m.type_detecte ? TYPES_EMAIL[m.type_detecte] : "Non reconnu"}
          {m.regle_nom && <span className="text-muted-foreground"> · règle « {m.regle_nom} »</span>}
        </dd>
        <dt className="text-muted-foreground">Statut</dt>
        <dd>{LIBELLES_STATUT[m.statut_traitement]}</dd>
        {m.article_id && (
          <>
            <dt className="text-muted-foreground">Article</dt>
            <dd>
              <Link href={`/stock/${m.article_id}`} className="hover:underline">
                {m.article_nom}
              </Link>
            </dd>
          </>
        )}
      </dl>

      {donnees.length > 0 && (
        <div className="rounded-lg bg-muted/50 p-3">
          <p className="mb-1.5 text-xs font-medium text-muted-foreground">Données extraites</p>
          <dl className="grid grid-cols-[130px_1fr] gap-x-3 gap-y-1 text-sm">
            {donnees.map(([k, v]) => (
              <div key={k} className="contents">
                <dt className="text-muted-foreground">{k.replace("_", " ")}</dt>
                <dd className="truncate font-mono text-xs leading-5">{String(v)}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      <div className="flex flex-wrap gap-2">
        <Select onValueChange={(v) => classer.mutate(v as TypeEmail)}>
          <SelectTrigger size="sm" className="w-48" aria-label="Classer comme">
            <SelectValue placeholder="Classer comme…" />
          </SelectTrigger>
          <SelectContent>
            {Object.entries(TYPES_EMAIL).map(([v, l]) => (
              <SelectItem key={v} value={v}>
                {l}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {m.type_detecte && m.type_detecte !== "vente" && m.statut_traitement === "nouveau" && (
          <SelecteurArticle
            libelle="Rattacher à un article…"
            onChoix={(a) => rattacher.mutate(a.id)}
            desactive={rattacher.isPending}
          />
        )}
        <Button variant="outline" size="sm" onClick={() => suggestion.mutate()} disabled={suggestion.isPending}>
          {suggestion.isPending ? <Loader2 className="animate-spin" /> : <Wand2 />}
          Créer une règle à partir de ce mail
        </Button>
        {m.statut_traitement !== "ignore" && (
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              classer.mutate(null);
              fermer();
            }}
          >
            <X /> Ignorer
          </Button>
        )}
      </div>

      {m.pieces_jointes.length > 0 && (
        <ul className="space-y-1">
          {m.pieces_jointes.map((p) => (
            <li key={p.id}>
              <a
                href={`/api/pieces-jointes/${p.id}`}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-sm hover:underline"
              >
                <Paperclip className="size-3.5" /> {p.nom}
              </a>
            </li>
          ))}
        </ul>
      )}

      <div>
        <p className="mb-1.5 text-xs font-medium text-muted-foreground">Contenu</p>
        {m.corps_html ? (
          // Aperçu isolé : aucun script, aucun accès à l'app.
          <iframe
            title="Contenu du mail"
            sandbox=""
            srcDoc={m.corps_html}
            className="h-[55dvh] w-full rounded-lg border bg-white"
          />
        ) : (
          <pre className="max-h-[55dvh] overflow-auto rounded-lg border p-3 font-sans text-sm whitespace-pre-wrap">
            {m.corps_texte}
          </pre>
        )}
      </div>

      {regle && (
        <EditeurRegle
          ouvert={!!regle}
          setOuvert={(v) => !v && setRegle(null)}
          initiale={regle}
          emailId={id}
          apresEnregistrement={invalider}
        />
      )}
    </div>
  );
}

export default function PageMails() {
  const [onglet, setOnglet] = useState<Onglet>("a_classer");
  const [ouvert, setOuvert] = useState<number | null>(null);
  const [compte, setCompte] = useState("tous");
  const { data: comptes } = useComptes();
  const plusieursComptes = (comptes?.length ?? 0) > 1;
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["emails", onglet, compte],
    queryFn: () =>
      api<{ items: EmailResume[]; total: number; compteurs: Record<string, number> }>("/emails", {
        params: { ...FILTRES[onglet], compte: compte === "tous" ? undefined : compte, taille_page: 100 },
      }),
  });
  const compteurs = data?.compteurs ?? {};

  return (
    <>
      <EnTetePage
        titre="Mails"
        description="Mails Vinted lus dans ta boîte (jamais modifiés ni marqués comme lus)"
        actions={<BoutonSynchro />}
      />
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Tabs value={onglet} onValueChange={(v) => setOnglet(v as Onglet)}>
          <TabsList>
            <TabsTrigger value="a_classer">
              Non classés {!!compteurs.a_classer && <span className="ml-1 tabular-nums">({compteurs.a_classer})</span>}
            </TabsTrigger>
            <TabsTrigger value="a_rattacher">À rattacher</TabsTrigger>
            <TabsTrigger value="tous">Tous</TabsTrigger>
          </TabsList>
        </Tabs>
        {plusieursComptes && (
          <Select value={compte} onValueChange={setCompte}>
            <SelectTrigger size="sm" className="w-48" aria-label="Compte Vinted">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="tous">Tous les comptes</SelectItem>
              {comptes?.map((c) => (
                <SelectItem key={c.id} value={String(c.id)}>
                  {c.nom}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </div>

      {error ? (
        <MessageErreur erreur={error} reessayer={() => refetch()} />
      ) : isLoading ? (
        <LignesSquelette n={6} />
      ) : !data?.items.length ? (
        <EtatVide
          icone={Inbox}
          titre={onglet === "tous" ? "Aucun mail synchronisé" : "Rien à traiter ici"}
          texte={
            onglet === "tous"
              ? "Configure ta boîte mail dans les paramètres, puis lance une synchronisation."
              : "Tous les mails reçus ont été reconnus et traités."
          }
          action={onglet === "tous" ? { libelle: "Configurer les mails", href: "/parametres?onglet=mails" } : undefined}
        />
      ) : (
        <ul className="divide-y rounded-xl border bg-card">
          {data.items.map((m) => (
            <li key={m.id}>
              <button
                type="button"
                onClick={() => setOuvert(m.id)}
                className="flex w-full flex-col gap-1 px-4 py-3 text-left outline-none hover:bg-muted/50 focus-visible:bg-muted/50 sm:flex-row sm:items-center sm:gap-4"
              >
                <span className="w-32 shrink-0 text-xs text-muted-foreground tabular-nums">
                  {formatDateHeure(m.date)}
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm font-medium">{m.sujet || "(sans sujet)"}</span>
                  <span className="block truncate text-xs text-muted-foreground">{m.extrait}</span>
                </span>
                {plusieursComptes && <BadgeCompte nom={m.compte} />}
                <span
                  className={cn(
                    "w-fit shrink-0 rounded-full px-2 py-0.5 text-xs font-medium",
                    m.type_detecte ? "bg-muted" : "bg-amber-50 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
                  )}
                >
                  {m.type_detecte ? TYPES_EMAIL[m.type_detecte] : "Non classé"}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}

      <Sheet open={ouvert !== null} onOpenChange={(o) => !o && setOuvert(null)}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
          <SheetHeader>
            <SheetTitle className="pr-6">{data?.items.find((m) => m.id === ouvert)?.sujet ?? "Mail"}</SheetTitle>
            <SheetDescription className="sr-only">Détail du mail</SheetDescription>
          </SheetHeader>
          <div className="px-4 pb-6">
            {ouvert !== null && <DetailMail id={ouvert} fermer={() => setOuvert(null)} />}
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
