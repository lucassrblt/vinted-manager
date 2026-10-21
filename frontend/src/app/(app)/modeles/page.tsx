"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookText, Loader2, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { EnTetePage, EtatVide, LignesSquelette } from "@/components/commun";
import { Champ } from "@/components/stock/dialog-article";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";

type Ressource = "modeles-annonce" | "modeles-reponse";
type Brouillon = Record<string, string | number | null>;

const CHAMPS: Record<Ressource, { cle: string; libelle: string; long?: boolean }[]> = {
  "modeles-annonce": [
    { cle: "nom", libelle: "Nom" },
    { cle: "categorie", libelle: "Catégorie (identique à celle des articles)" },
    { cle: "structure_titre", libelle: "Structure du titre" },
    { cle: "structure_description", libelle: "Structure de la description", long: true },
    { cle: "mots_cles", libelle: "Mots-clés" },
  ],
  "modeles-reponse": [
    { cle: "nom", libelle: "Nom" },
    { cle: "contexte", libelle: "Contexte (remerciement, demande de lot, question taille…)" },
    { cle: "texte", libelle: "Texte", long: true },
  ],
};

function Liste({ ressource }: { ressource: Ressource }) {
  const qc = useQueryClient();
  const [edition, setEdition] = useState<Brouillon | null>(null);
  const { data, isLoading } = useQuery({ queryKey: [ressource], queryFn: () => api<Brouillon[]>(`/${ressource}`) });
  const enregistrer = useMutation({
    mutationFn: (b: Brouillon) => {
      const { id, ...corps } = b;
      return api(id ? `/${ressource}/${id}` : `/${ressource}`, { method: id ? "PUT" : "POST", body: corps });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [ressource] });
      toast.success("Modèle enregistré");
      setEdition(null);
    },
    onError: (e: Error) => toast.error(e.message),
  });
  const supprimer = useMutation({
    mutationFn: (id: number) => api(`/${ressource}/${id}`, { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: [ressource] }),
  });
  const champs = CHAMPS[ressource];
  const vide = Object.fromEntries(champs.map((c) => [c.cle, ""]));

  return (
    <>
      <div className="mb-3 flex justify-end">
        <Button onClick={() => setEdition(vide)}>
          <Plus /> Nouveau modèle
        </Button>
      </div>
      {isLoading ? (
        <LignesSquelette n={4} />
      ) : !data?.length ? (
        <EtatVide icone={BookText} titre="Aucun modèle" />
      ) : (
        <ul className="divide-y rounded-xl border bg-card">
          {data.map((m) => (
            <li key={String(m.id)} className="flex items-start gap-3 px-4 py-3">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium">{m.nom}</p>
                <p className="line-clamp-2 text-xs text-muted-foreground">
                  {ressource === "modeles-annonce"
                    ? `${m.categorie ?? "Toutes catégories"} · ${m.structure_titre ?? ""}`
                    : `${m.contexte} · ${m.texte}`}
                </p>
              </div>
              <Button variant="ghost" size="icon-sm" aria-label="Modifier" onClick={() => setEdition(m)}>
                <Pencil />
              </Button>
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Supprimer"
                onClick={() => confirm(`Supprimer « ${m.nom} » ?`) && supprimer.mutate(Number(m.id))}
              >
                <Trash2 />
              </Button>
            </li>
          ))}
        </ul>
      )}
      <Dialog open={!!edition} onOpenChange={(o) => !o && setEdition(null)}>
        <DialogContent className="sm:max-w-lg">
          <DialogHeader>
            <DialogTitle>{edition?.id ? "Modifier le modèle" : "Nouveau modèle"}</DialogTitle>
          </DialogHeader>
          {edition && (
            <div className="space-y-3">
              {champs.map((c) => (
                <Champ key={c.cle} id={`${ressource}-${c.cle}`} libelle={c.libelle}>
                  {c.long ? (
                    <Textarea
                      id={`${ressource}-${c.cle}`}
                      rows={4}
                      value={String(edition[c.cle] ?? "")}
                      onChange={(e) => setEdition({ ...edition, [c.cle]: e.target.value })}
                    />
                  ) : (
                    <Input
                      id={`${ressource}-${c.cle}`}
                      value={String(edition[c.cle] ?? "")}
                      onChange={(e) => setEdition({ ...edition, [c.cle]: e.target.value })}
                    />
                  )}
                </Champ>
              ))}
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setEdition(null)}>
              Annuler
            </Button>
            <Button
              onClick={() => edition && enregistrer.mutate(edition)}
              disabled={enregistrer.isPending || !edition?.nom}
            >
              {enregistrer.isPending && <Loader2 className="animate-spin" />}
              Enregistrer
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

export default function PageModeles() {
  return (
    <>
      <EnTetePage titre="Modèles" description="Guident l'IA pour les annonces et les réponses aux acheteurs" />
      <Tabs defaultValue="annonce">
        <TabsList>
          <TabsTrigger value="annonce">Annonces</TabsTrigger>
          <TabsTrigger value="reponse">Réponses</TabsTrigger>
        </TabsList>
        <TabsContent value="annonce" className="mt-4">
          <Liste ressource="modeles-annonce" />
        </TabsContent>
        <TabsContent value="reponse" className="mt-4">
          <Liste ressource="modeles-reponse" />
        </TabsContent>
      </Tabs>
    </>
  );
}
