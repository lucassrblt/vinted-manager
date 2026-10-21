"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, HandCoins, Loader2, MessageCircle, Sparkles, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { toast } from "sonner";

import { EnTetePage, EtatVide, LignesSquelette, MessageErreur } from "@/components/commun";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { copier } from "@/lib/copier";
import { formatCoefficient, formatDateHeure, formatEuros } from "@/lib/format";
import type { AnalyseOffre, GroupeMessages, MessageAcheteur } from "@/lib/types";
import { cn } from "@/lib/utils";

const DECISIONS: Record<AnalyseOffre["decision"], { libelle: string; classe: string }> = {
  accepter: { libelle: "Accepter", classe: "bg-brand-soft text-brand" },
  contre_proposer: {
    libelle: "Contre-proposer",
    classe: "bg-amber-50 text-amber-800 dark:bg-amber-950/60 dark:text-amber-300",
  },
  refuser: { libelle: "Refuser poliment", classe: "bg-red-50 text-red-700 dark:bg-red-950/60 dark:text-red-300" },
};

function BlocOffre({ a }: { a: AnalyseOffre }) {
  const d = DECISIONS[a.decision];
  return (
    <div className="rounded-lg border bg-muted/30 p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <HandCoins className="size-4 text-muted-foreground" />
        <span>
          Offre <strong className="tabular-nums">{formatEuros(a.montant_offre)}</strong>
          {a.prix_affiche && <span className="text-muted-foreground"> sur {formatEuros(a.prix_affiche)}</span>}
        </span>
        <span className={cn("ml-auto rounded-full px-2 py-0.5 text-xs font-semibold", d.classe)}>
          {d.libelle}
          {a.montant_propose && ` à ${formatEuros(a.montant_propose)}`}
        </span>
      </div>
      <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
        <div>
          <dt className="text-muted-foreground">Marge si acceptée</dt>
          <dd className={cn("font-medium tabular-nums", Number(a.marge_si_accepte) < 0 && "text-red-600")}>
            {formatEuros(a.marge_si_accepte)}
          </dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Coefficient</dt>
          <dd className="font-medium tabular-nums">{formatCoefficient(a.coefficient_si_accepte)}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Prix minimum</dt>
          <dd className="font-medium tabular-nums">{formatEuros(a.prix_plancher)}</dd>
        </div>
        {a.marge_proposee && (
          <div>
            <dt className="text-muted-foreground">Marge contre-proposée</dt>
            <dd className="font-medium tabular-nums">{formatEuros(a.marge_proposee)}</dd>
          </div>
        )}
      </dl>
      <p className="mt-2 text-xs text-muted-foreground">{a.explication}</p>
    </div>
  );
}

function CarteMessage({ m }: { m: MessageAcheteur }) {
  const qc = useQueryClient();
  const [reponse, setReponse] = useState(m.reponse_finale ?? m.reponse_suggeree ?? "");
  const invalider = () => {
    qc.invalidateQueries({ queryKey: ["messages"] });
    qc.invalidateQueries({ queryKey: ["dashboard"] });
  };
  const suggestion = useMutation({
    mutationFn: () => api<MessageAcheteur>(`/messages/${m.id}/suggestion`, { method: "POST" }),
    onSuccess: (r) => {
      setReponse(r.reponse_suggeree ?? "");
      invalider();
    },
    onError: (e: Error) => toast.error(e.message, { duration: 8000 }),
  });
  const maj = useMutation({
    mutationFn: (corps: { statut: string; reponse_finale?: string }) =>
      api<MessageAcheteur>(`/messages/${m.id}`, { method: "PATCH", body: corps }),
    onSuccess: (r) => {
      invalider();
      toast.success(r.statut === "repondu" ? "Marqué comme répondu" : "Message ignoré");
    },
  });

  return (
    <li className="space-y-3 p-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="font-medium">{m.acheteur ?? "Acheteur"}</span>
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs">{m.type === "offre" ? "Offre" : "Message"}</span>
        <span className="ml-auto text-xs text-muted-foreground tabular-nums">{formatDateHeure(m.created_at)}</span>
      </div>
      {m.extrait && (
        <p className="line-clamp-4 rounded-lg bg-muted/40 px-3 py-2 text-sm whitespace-pre-line">{m.extrait}</p>
      )}
      {m.analyse && <BlocOffre a={m.analyse} />}
      {m.statut === "a_traiter" ? (
        <>
          <Textarea
            rows={3}
            value={reponse}
            onChange={(e) => setReponse(e.target.value)}
            placeholder="Ta réponse (rien n'est envoyé automatiquement)"
            aria-label="Réponse"
          />
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => suggestion.mutate()} disabled={suggestion.isPending}>
              {suggestion.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />}
              {m.reponse_suggeree ? "Nouvelle suggestion" : "Suggérer une réponse"}
            </Button>
            <Button variant="outline" size="sm" disabled={!reponse} onClick={() => copier(reponse, "Réponse")}>
              <Copy /> Copier
            </Button>
            <Button
              size="sm"
              onClick={() => maj.mutate({ statut: "repondu", reponse_finale: reponse })}
              disabled={maj.isPending}
            >
              <Check /> Marquer répondu
            </Button>
            <Button variant="ghost" size="sm" onClick={() => maj.mutate({ statut: "ignore" })}>
              <X /> Ignorer
            </Button>
          </div>
        </>
      ) : (
        m.reponse_finale && <p className="text-sm text-muted-foreground">Répondu : « {m.reponse_finale} »</p>
      )}
    </li>
  );
}

export default function PageMessages() {
  const [onglet, setOnglet] = useState<"a_traiter" | "traites">("a_traiter");
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["messages", onglet],
    queryFn: () =>
      api<GroupeMessages[]>("/messages", {
        params: { statut: onglet === "a_traiter" ? ["a_traiter"] : ["repondu", "ignore"] },
      }),
  });
  return (
    <>
      <EnTetePage
        titre="Messages"
        description="Messages et offres reçus, avec une réponse suggérée. Rien n'est envoyé automatiquement."
      />
      <Tabs value={onglet} onValueChange={(v) => setOnglet(v as typeof onglet)} className="mb-4">
        <TabsList>
          <TabsTrigger value="a_traiter">À traiter</TabsTrigger>
          <TabsTrigger value="traites">Traités</TabsTrigger>
        </TabsList>
      </Tabs>
      {error ? (
        <MessageErreur erreur={error} reessayer={() => refetch()} />
      ) : isLoading ? (
        <LignesSquelette n={4} />
      ) : !data?.length ? (
        <EtatVide
          icone={MessageCircle}
          titre={onglet === "a_traiter" ? "Aucun message à traiter" : "Aucun message traité"}
          texte="Les messages et offres Vinted reçus par mail arrivent ici automatiquement."
        />
      ) : (
        <div className="space-y-4">
          {data.map((g) => (
            <section key={g.article?.id ?? "sans"} className="overflow-hidden rounded-xl border bg-card">
              <header className="flex flex-wrap items-center gap-2 border-b bg-muted/30 px-4 py-2.5 text-sm">
                {g.article ? (
                  <>
                    <Link href={`/stock/${g.article.id}`} className="font-medium hover:underline">
                      {g.article.nom}
                    </Link>
                    <span className="text-muted-foreground tabular-nums">
                      {[g.article.taille, formatEuros(g.article.prix_vente)].filter(Boolean).join(" · ")}
                    </span>
                  </>
                ) : (
                  <span className="text-muted-foreground">Article non identifié</span>
                )}
              </header>
              <ul className="divide-y">
                {g.messages.map((m) => (
                  <CarteMessage key={m.id} m={m} />
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </>
  );
}
