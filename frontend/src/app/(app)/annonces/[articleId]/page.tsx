"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeft,
  Check,
  ChevronDown,
  Copy,
  Download,
  Info,
  Loader2,
  RefreshCw,
  Rocket,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { ChoixProvenance, ResumeProvenance } from "@/components/annonces/provenance";
import { LignesSquelette, MessageErreur, StatutBadge } from "@/components/commun";
import { PhotosArticle } from "@/components/photos/photos-article";
import { Champ } from "@/components/stock/dialog-article";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { copier } from "@/lib/copier";
import { formatCoefficient, formatEuros, saisieVersDecimal } from "@/lib/format";
import { useInvaliderStock } from "@/lib/queries";
import { ETATS } from "@/lib/statuts";
import type { AnnonceGeneree, Article, Etat, FicheAnnonce, ModeleAnnonce } from "@/lib/types";
import { cn } from "@/lib/utils";

const TITRE_MAX = 60;

interface Fiche {
  marque: string;
  modele: string;
  categorie: string;
  taille: string;
  couleur: string;
  etat: Etat | "";
  matiere: string;
  defauts: string;
  modele_annonce_id: string;
}

type Cible = "tout" | "titre" | "description";

/** Provenance pas encore choisie : article créé depuis les photos, sans batch, prix d'achat ni statut perso. */
function provenanceAChoisir(a: Article): boolean {
  return a.statut === "recu_a_publier" && !a.perso && !a.batch_id && a.prix_achat_net === null;
}

export default function GenerateurAnnonce() {
  const id = Number(useParams<{ articleId: string }>().articleId);
  const router = useRouter();
  const nouvelle = useSearchParams().get("nouvelle") === "1";
  const invalider = useInvaliderStock();
  const { data, error, refetch } = useQuery({
    queryKey: ["annonce", id],
    queryFn: () => api<FicheAnnonce>(`/annonces/${id}`),
  });
  const modeles = useQuery({ queryKey: ["modeles-annonce"], queryFn: () => api<ModeleAnnonce[]>("/modeles-annonce") });

  const [fiche, setFiche] = useState<Fiche | null>(null);
  const [annonce, setAnnonce] = useState<AnnonceGeneree | null>(null);
  const [prix, setPrix] = useState("");
  const [essai, setEssai] = useState(0);
  const [modifierProvenance, setModifierProvenance] = useState(false);
  const [ficheOuverte, setFicheOuverte] = useState(false);

  useEffect(() => {
    if (!data || fiche) return;
    const a = data.article;
    setFiche({
      marque: a.marque ?? "",
      modele: a.modele ?? "",
      categorie: a.categorie ?? "",
      taille: a.taille ?? "",
      couleur: a.couleur ?? "",
      etat: a.etat ?? "",
      matiere: a.matiere ?? "",
      defauts: a.defauts ?? "",
      modele_annonce_id: data.modele_id ? String(data.modele_id) : "",
    });
    if (a.titre_annonce || a.description_annonce)
      setAnnonce({
        titre: a.titre_annonce ?? "",
        description: a.description_annonce ?? "",
        mots_cles: (a.mots_cles_annonce ?? "")
          .split(",")
          .map((m) => m.trim())
          .filter(Boolean),
      });
    const p = a.prix_vente_cible ?? data.prix_conseille.prix;
    setPrix(p ? String(Number(p)).replace(".", ",") : "");
  }, [data, fiche]);

  const generation = useMutation({
    mutationFn: ({ n, cible, consigne }: { n: number; cible: Cible; consigne?: string }) =>
      api<AnnonceGeneree>(`/annonces/${id}/generer`, {
        body: {
          ...fiche,
          etat: fiche?.etat || null,
          modele_annonce_id: fiche?.modele_annonce_id ? Number(fiche.modele_annonce_id) : null,
          essai: n,
          cible,
          consigne: consigne ?? null,
        },
      }),
    onSuccess: (r, { cible }) => {
      // On ne remplace que la partie demandée : les retouches faites à la main sur l'autre restent.
      setAnnonce((ancienne) => ({
        titre: cible === "description" && ancienne ? ancienne.titre : r.titre,
        description: cible === "titre" && ancienne ? ancienne.description : r.description,
        mots_cles: r.mots_cles,
      }));
      invalider();
    },
    onError: (e: Error) => toast.error(e.message, { duration: 8000 }),
  });
  const regenerer = (cible: Cible, consigne?: string) => {
    const n = essai + 1;
    setEssai(n);
    generation.mutate({ n, cible, consigne });
  };

  const publication = useMutation({
    mutationFn: () =>
      api(`/annonces/${id}/publier`, {
        body: { prix: saisieVersDecimal(prix), titre: annonce?.titre, description: annonce?.description },
      }),
    onSuccess: () => {
      invalider();
      toast.success("Article en ligne : date et heure de publication enregistrées");
      router.push("/annonces/nouvelle");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (error) return <MessageErreur erreur={error} reessayer={() => refetch()} />;
  if (!data || !fiche) return <LignesSquelette n={10} />;
  const a = data.article;
  const pc = data.prix_conseille;
  const maj = (cle: keyof Fiche) => (v: string) => setFiche({ ...fiche, [cle]: v });
  const prixValide = !prix || saisieVersDecimal(prix) !== null;
  const coeffPrix =
    saisieVersDecimal(prix) && a.prix_achat_net && Number(a.prix_achat_net) > 0
      ? Number(saisieVersDecimal(prix)) / Number(a.prix_achat_net)
      : null;
  const choisirProvenance = modifierProvenance || provenanceAChoisir(a);
  const enCours = generation.isPending ? generation.variables?.cible : null;

  return (
    <div className="space-y-5">
      <div>
        <Link
          href="/annonces"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" /> Annonces
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">{annonce?.titre || a.nom}</h1>
          <StatutBadge statut={a.statut} />
        </div>
        {!choisirProvenance && (
          <div className="mt-1.5">
            <ResumeProvenance article={a} onModifier={() => setModifierProvenance(true)} />
          </div>
        )}
      </div>

      {!data.ia_disponible && (
        <p className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          <Info className="mt-0.5 size-4 shrink-0" />
          L&apos;IA n&apos;est pas configurée sur le serveur (variable ANTHROPIC_API_KEY). Tu peux quand même rédiger
          l&apos;annonce à la main et la publier.
        </p>
      )}
      {nouvelle && !data.retouche_possible && (
        <p className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          <Info className="mt-0.5 size-4 shrink-0" />
          Retouche des photos non lancée : ajoute la photo du tapis dans Paramètres → Photos (et REPLICATE_API_TOKEN sur
          le serveur).
        </p>
      )}

      {choisirProvenance && (
        <ChoixProvenance
          article={a}
          onChoisi={(nouvelId) => {
            setModifierProvenance(false);
            if (nouvelId !== id) router.replace(`/annonces/${nouvelId}`);
            else refetch();
          }}
        />
      )}

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
        <section className="rounded-xl border bg-card p-4 md:p-5">
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">Photos</h2>
            <Button variant="outline" size="sm" asChild>
              <a href={`/api/articles/${id}/photos.zip`} download>
                <Download /> Télécharger pour Vinted
              </a>
            </Button>
          </div>
          <PhotosArticle articleId={id} />
        </section>

        <div className="space-y-5">
          <section className="space-y-3 rounded-xl border bg-card p-4 md:p-5">
            <h2 className="text-sm font-semibold">Annonce</h2>
            {generation.isPending && !annonce ? (
              <LignesSquelette n={4} />
            ) : (
              <>
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <label htmlFor="a-titre" className="text-sm font-medium">
                      Titre
                    </label>
                    <span className="flex items-center gap-1">
                      <span
                        className={cn(
                          "text-xs tabular-nums",
                          (annonce?.titre.length ?? 0) > TITRE_MAX ? "text-destructive" : "text-muted-foreground",
                        )}
                      >
                        {annonce?.titre.length ?? 0}/{TITRE_MAX}
                      </span>
                      <Button
                        variant="ghost"
                        size="xs"
                        disabled={generation.isPending || !data.ia_disponible}
                        onClick={() =>
                          regenerer("titre", annonce?.titre ? `un autre titre que « ${annonce.titre} »` : undefined)
                        }
                      >
                        <RefreshCw className={cn(enCours === "titre" && "animate-spin")} /> Autre titre
                      </Button>
                    </span>
                  </div>
                  <div className="flex gap-2">
                    <Input
                      id="a-titre"
                      value={annonce?.titre ?? ""}
                      onChange={(e) =>
                        setAnnonce({
                          titre: e.target.value,
                          description: annonce?.description ?? "",
                          mots_cles: annonce?.mots_cles ?? [],
                        })
                      }
                    />
                    <Button
                      variant="outline"
                      size="icon"
                      aria-label="Copier le titre"
                      disabled={!annonce?.titre}
                      onClick={() => copier(annonce!.titre, "Titre")}
                    >
                      <Copy />
                    </Button>
                  </div>
                </div>
                <div className="space-y-1.5">
                  <div className="flex flex-wrap items-center justify-between gap-1">
                    <label htmlFor="a-description" className="text-sm font-medium">
                      Description
                    </label>
                    <span className="flex flex-wrap items-center gap-1">
                      <Button
                        variant="ghost"
                        size="xs"
                        disabled={generation.isPending || !data.ia_disponible}
                        onClick={() => regenerer("description", "encore plus court et simple")}
                      >
                        Plus court
                      </Button>
                      <Button
                        variant="ghost"
                        size="xs"
                        disabled={generation.isPending || !data.ia_disponible}
                        onClick={() =>
                          regenerer(
                            "description",
                            annonce?.description
                              ? `même style, mais formulé autrement que : « ${annonce.description} »`
                              : undefined,
                          )
                        }
                      >
                        <RefreshCw className={cn(enCours === "description" && "animate-spin")} /> Autre version
                      </Button>
                    </span>
                  </div>
                  <Textarea
                    id="a-description"
                    rows={5}
                    value={annonce?.description ?? ""}
                    onChange={(e) =>
                      setAnnonce({
                        titre: annonce?.titre ?? "",
                        description: e.target.value,
                        mots_cles: annonce?.mots_cles ?? [],
                      })
                    }
                  />
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-full"
                    disabled={!annonce?.description}
                    onClick={() => copier(annonce!.description, "Description")}
                  >
                    <Copy /> Copier la description
                  </Button>
                </div>
                {!annonce && (
                  <Button
                    className="w-full bg-brand text-brand-foreground hover:bg-brand/90"
                    onClick={() => regenerer("tout")}
                    disabled={generation.isPending || !data.ia_disponible}
                  >
                    {generation.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />}
                    Rédiger l&apos;annonce
                  </Button>
                )}
              </>
            )}
          </section>

          <section className="space-y-3 rounded-xl border bg-card p-4 md:p-5">
            <h2 className="text-sm font-semibold">Prix</h2>
            <div className="rounded-lg bg-muted/50 p-3 text-sm">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-muted-foreground">
                  {pc.prix ? (pc.estimation ? "Prix estimé" : "Prix conseillé") : "Proposé par l'IA"}
                </span>
                <span className="text-lg font-semibold tabular-nums">{formatEuros(pc.prix ?? a.prix_vente_cible)}</span>
              </div>
              {pc.fourchette_basse && (
                <p className="text-xs text-muted-foreground tabular-nums">
                  Fourchette {formatEuros(pc.fourchette_basse)} – {formatEuros(pc.fourchette_haute)}
                </p>
              )}
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                {!pc.prix && a.prix_vente_cible
                  ? "Pas assez de ventes comparables dans ton historique : estimation de l'IA d'après l'article et tes ventes passées."
                  : pc.raisonnement}
              </p>
            </div>
            <div className="flex items-end gap-2">
              <Champ
                id="a-prix"
                libelle="Prix de mise en ligne (€)"
                erreur={prixValide ? null : "Montant invalide."}
                className="flex-1"
              >
                <Input id="a-prix" inputMode="decimal" value={prix} onChange={(e) => setPrix(e.target.value)} />
              </Champ>
              {pc.prix && (
                <Button variant="outline" onClick={() => setPrix(String(Number(pc.prix)).replace(".", ","))}>
                  <Check /> Prix conseillé
                </Button>
              )}
            </div>
            {coeffPrix !== null && (
              <p
                className={cn(
                  "text-xs tabular-nums",
                  coeffPrix < 2 ? "text-red-600 dark:text-red-400" : "text-muted-foreground",
                )}
              >
                Coefficient {formatCoefficient(coeffPrix)} · marge{" "}
                {formatEuros(Number(saisieVersDecimal(prix)) - Number(a.prix_achat_net))}
                {coeffPrix < 2 && " · sous l'objectif"}
              </p>
            )}
            <Button
              size="lg"
              className="w-full"
              onClick={() => publication.mutate()}
              disabled={
                publication.isPending ||
                !prixValide ||
                choisirProvenance ||
                !["recu_a_publier", "en_ligne", "retourne"].includes(a.statut)
              }
            >
              {publication.isPending ? <Loader2 className="animate-spin" /> : <Rocket />}
              Publié sur Vinted
            </Button>
            {choisirProvenance && (
              <p className="text-center text-xs text-muted-foreground">Choisis d&apos;abord la provenance.</p>
            )}
          </section>
        </div>
      </div>

      <section className="rounded-xl border bg-card">
        <button
          type="button"
          onClick={() => setFicheOuverte((o) => !o)}
          aria-expanded={ficheOuverte}
          className="flex w-full items-center justify-between gap-2 p-4 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50 md:px-5"
        >
          <span>
            <span className="block text-sm font-semibold">Fiche de l&apos;article</span>
            <span className="text-xs text-muted-foreground">
              {[
                fiche.marque,
                fiche.categorie,
                fiche.taille && `taille ${fiche.taille}`,
                fiche.couleur,
                ETATS[fiche.etat as Etat],
              ]
                .filter(Boolean)
                .join(" · ") || "Lue sur les photos : à compléter si besoin"}
            </span>
          </span>
          <ChevronDown className={cn("size-4 shrink-0 transition-transform", ficheOuverte && "rotate-180")} />
        </button>
        {ficheOuverte && (
          <div className="space-y-4 border-t p-4 md:p-5">
            <p className="text-xs text-muted-foreground">
              L&apos;IA n&apos;utilise que ces informations : ce qui n&apos;est pas renseigné ne sera jamais affirmé.
            </p>
            <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
              <Champ id="f-marque" libelle="Marque">
                <Input id="f-marque" value={fiche.marque} onChange={(e) => maj("marque")(e.target.value)} />
              </Champ>
              <Champ id="f-categorie" libelle="Catégorie">
                <Input id="f-categorie" value={fiche.categorie} onChange={(e) => maj("categorie")(e.target.value)} />
              </Champ>
              <Champ id="f-taille" libelle="Taille">
                <Input id="f-taille" value={fiche.taille} onChange={(e) => maj("taille")(e.target.value)} />
              </Champ>
              <Champ id="f-couleur" libelle="Couleur">
                <Input id="f-couleur" value={fiche.couleur} onChange={(e) => maj("couleur")(e.target.value)} />
              </Champ>
              <Champ id="f-etat" libelle="État">
                <Select value={fiche.etat} onValueChange={maj("etat")}>
                  <SelectTrigger id="f-etat" className="w-full">
                    <SelectValue placeholder="Non renseigné" />
                  </SelectTrigger>
                  <SelectContent>
                    {Object.entries(ETATS).map(([v, l]) => (
                      <SelectItem key={v} value={v}>
                        {l}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Champ>
              <Champ id="f-modele" libelle="Modèle">
                <Input id="f-modele" value={fiche.modele} onChange={(e) => maj("modele")(e.target.value)} />
              </Champ>
              <Champ id="f-matiere" libelle="Matière">
                <Input id="f-matiere" value={fiche.matiere} onChange={(e) => maj("matiere")(e.target.value)} />
              </Champ>
              <Champ id="f-modele-annonce" libelle="Modèle d'annonce">
                <Select value={fiche.modele_annonce_id} onValueChange={maj("modele_annonce_id")}>
                  <SelectTrigger id="f-modele-annonce" className="w-full">
                    <SelectValue placeholder="Aucun" />
                  </SelectTrigger>
                  <SelectContent>
                    {modeles.data?.map((m) => (
                      <SelectItem key={m.id} value={String(m.id)}>
                        {m.nom}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Champ>
              <Champ id="f-defauts" libelle="Défauts" className="col-span-2 md:col-span-4">
                <Input
                  id="f-defauts"
                  value={fiche.defauts}
                  onChange={(e) => maj("defauts")(e.target.value)}
                  placeholder="Aucun si vide"
                />
              </Champ>
            </div>
            <Button
              variant="outline"
              onClick={() => regenerer("tout")}
              disabled={generation.isPending || !data.ia_disponible}
            >
              {enCours === "tout" ? <Loader2 className="animate-spin" /> : <Sparkles />}
              Réécrire l&apos;annonce avec cette fiche
            </Button>
          </div>
        )}
      </section>
    </div>
  );
}
