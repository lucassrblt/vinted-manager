"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowLeft, Check, Copy, Info, Loader2, RefreshCw, Rocket, Sparkles } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { toast } from "sonner";

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
import type { AnnonceGeneree, Etat, FicheAnnonce, ModeleAnnonce } from "@/lib/types";
import { cn } from "@/lib/utils";

const MESURES = [
  { cle: "longueur", libelle: "Longueur (cm)" },
  { cle: "largeur_aisselles", libelle: "Largeur aisselles (cm)" },
  { cle: "epaules", libelle: "Épaules (cm)" },
  { cle: "manches", libelle: "Manches (cm)" },
  { cle: "tour_de_taille", libelle: "Tour de taille (cm)" },
  { cle: "entrejambe", libelle: "Entrejambe (cm)" },
];
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
  mesures: Record<string, string>;
  modele_annonce_id: string;
}

export default function GenerateurAnnonce() {
  const id = Number(useParams<{ articleId: string }>().articleId);
  const router = useRouter();
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
      mesures: Object.fromEntries(Object.entries(a.mesures ?? {}).map(([k, v]) => [k, String(v)])),
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
    mutationFn: (n: number) =>
      api<AnnonceGeneree>(`/annonces/${id}/generer`, {
        body: {
          ...fiche,
          etat: fiche?.etat || null,
          modele_annonce_id: fiche?.modele_annonce_id ? Number(fiche.modele_annonce_id) : null,
          essai: n,
        },
      }),
    onSuccess: (r) => {
      setAnnonce(r);
      invalider();
    },
    onError: (e: Error) => toast.error(e.message, { duration: 8000 }),
  });

  const publication = useMutation({
    mutationFn: () =>
      api(`/annonces/${id}/publier`, {
        body: { prix: saisieVersDecimal(prix), titre: annonce?.titre, description: annonce?.description },
      }),
    onSuccess: () => {
      invalider();
      toast.success("Article en ligne : date et heure de publication enregistrées");
      router.push("/annonces");
    },
    onError: (e: Error) => toast.error(e.message),
  });

  if (error) return <MessageErreur erreur={error} reessayer={() => refetch()} />;
  if (!data || !fiche) return <LignesSquelette n={10} />;
  const a = data.article;
  const pc = data.prix_conseille;
  const maj = (cle: keyof Fiche) => (v: string) => setFiche({ ...fiche, [cle]: v });
  const toutTexte = annonce
    ? `${annonce.titre}\n\n${annonce.description}${annonce.mots_cles.length ? `\n\n${annonce.mots_cles.map((m) => `#${m.replace(/\s+/g, "")}`).join(" ")}` : ""}`
    : "";
  const prixValide = !prix || saisieVersDecimal(prix) !== null;
  const coeffPrix =
    saisieVersDecimal(prix) && a.prix_achat_net ? Number(saisieVersDecimal(prix)) / Number(a.prix_achat_net) : null;

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
          <h1 className="text-2xl font-semibold tracking-tight">{a.nom}</h1>
          <StatutBadge statut={a.statut} />
        </div>
        <p className="mt-1 text-sm text-muted-foreground">Achat {formatEuros(a.prix_achat_net)}</p>
      </div>

      {!data.ia_disponible && (
        <p className="flex items-start gap-2 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
          <Info className="mt-0.5 size-4 shrink-0" />
          L&apos;IA n&apos;est pas configurée sur le serveur (variable ANTHROPIC_API_KEY). Tu peux quand même rédiger
          l&apos;annonce à la main et la publier.
        </p>
      )}

      <section className="rounded-xl border bg-card p-4 md:p-5">
        <h2 className="mb-3 text-sm font-semibold">Photos</h2>
        <PhotosArticle articleId={id} />
      </section>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <section className="space-y-4 rounded-xl border bg-card p-4 md:p-5">
          <h2 className="text-sm font-semibold">Fiche de l&apos;article</h2>
          <p className="-mt-2 text-xs text-muted-foreground">
            L&apos;IA n&apos;utilise que ces informations : ce qui n&apos;est pas renseigné ne sera jamais affirmé.
          </p>
          <div className="grid grid-cols-2 gap-3">
            <Champ id="f-marque" libelle="Marque">
              <Input id="f-marque" value={fiche.marque} onChange={(e) => maj("marque")(e.target.value)} />
            </Champ>
            <Champ id="f-modele" libelle="Modèle">
              <Input
                id="f-modele"
                value={fiche.modele}
                onChange={(e) => maj("modele")(e.target.value)}
                placeholder="Demi-zip polaire"
              />
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
            <Champ id="f-matiere" libelle="Matière">
              <Input
                id="f-matiere"
                value={fiche.matiere}
                onChange={(e) => maj("matiere")(e.target.value)}
                placeholder="Si indiquée sur l'étiquette"
              />
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
            <Champ id="f-defauts" libelle="Défauts éventuels" className="col-span-2">
              <Textarea
                id="f-defauts"
                rows={2}
                value={fiche.defauts}
                onChange={(e) => maj("defauts")(e.target.value)}
                placeholder="Aucun si vide"
              />
            </Champ>
          </div>
          <fieldset>
            <legend className="mb-2 text-sm font-medium">Mesures à plat (optionnel)</legend>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              {MESURES.map((m) => (
                <Champ key={m.cle} id={`m-${m.cle}`} libelle={m.libelle}>
                  <Input
                    id={`m-${m.cle}`}
                    inputMode="decimal"
                    value={fiche.mesures[m.cle] ?? ""}
                    onChange={(e) => setFiche({ ...fiche, mesures: { ...fiche.mesures, [m.cle]: e.target.value } })}
                  />
                </Champ>
              ))}
            </div>
          </fieldset>
          <Button
            className="w-full bg-brand text-brand-foreground hover:bg-brand/90"
            size="lg"
            onClick={() => {
              setEssai(0);
              generation.mutate(0);
            }}
            disabled={generation.isPending || !data.ia_disponible}
          >
            {generation.isPending ? <Loader2 className="animate-spin" /> : <Sparkles />}
            {annonce ? "Générer une nouvelle annonce" : "Générer l'annonce"}
          </Button>
        </section>

        <div className="space-y-5">
          <section className="space-y-3 rounded-xl border bg-card p-4 md:p-5">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-sm font-semibold">Annonce</h2>
              {annonce && (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    const n = essai + 1;
                    setEssai(n);
                    generation.mutate(n);
                  }}
                  disabled={generation.isPending || !data.ia_disponible}
                >
                  <RefreshCw className={cn(generation.isPending && "animate-spin")} /> Régénérer
                </Button>
              )}
            </div>
            {generation.isPending && !annonce ? (
              <LignesSquelette n={4} />
            ) : (
              <>
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label htmlFor="a-titre" className="text-sm font-medium">
                      Titre
                    </label>
                    <span
                      className={cn(
                        "text-xs tabular-nums",
                        (annonce?.titre.length ?? 0) > TITRE_MAX ? "text-destructive" : "text-muted-foreground",
                      )}
                    >
                      {annonce?.titre.length ?? 0}/{TITRE_MAX}
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
                  <div className="flex items-center justify-between">
                    <label htmlFor="a-description" className="text-sm font-medium">
                      Description
                    </label>
                    <Button
                      variant="ghost"
                      size="xs"
                      disabled={!annonce?.description}
                      onClick={() => copier(annonce!.description, "Description")}
                    >
                      <Copy /> Copier
                    </Button>
                  </div>
                  <Textarea
                    id="a-description"
                    rows={7}
                    value={annonce?.description ?? ""}
                    onChange={(e) =>
                      setAnnonce({
                        titre: annonce?.titre ?? "",
                        description: e.target.value,
                        mots_cles: annonce?.mots_cles ?? [],
                      })
                    }
                  />
                </div>
                {!!annonce?.mots_cles.length && (
                  <div className="flex flex-wrap gap-1.5">
                    {annonce.mots_cles.map((m) => (
                      <span key={m} className="rounded-full bg-muted px-2 py-0.5 text-xs">
                        #{m.replace(/\s+/g, "")}
                      </span>
                    ))}
                  </div>
                )}
                <Button
                  variant="outline"
                  className="w-full"
                  disabled={!annonce}
                  onClick={() => copier(toutTexte, "Annonce")}
                >
                  <Copy /> Copier tout
                </Button>
              </>
            )}
          </section>

          <section className="space-y-3 rounded-xl border bg-card p-4 md:p-5">
            <h2 className="text-sm font-semibold">Prix</h2>
            <div className="rounded-lg bg-muted/50 p-3 text-sm">
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-muted-foreground">{pc.estimation ? "Prix estimé" : "Prix conseillé"}</span>
                <span className="text-lg font-semibold tabular-nums">{formatEuros(pc.prix)}</span>
              </div>
              {pc.fourchette_basse && (
                <p className="text-xs text-muted-foreground tabular-nums">
                  Fourchette {formatEuros(pc.fourchette_basse)} – {formatEuros(pc.fourchette_haute)}
                </p>
              )}
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{pc.raisonnement}</p>
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
                publication.isPending || !prixValide || !["recu_a_publier", "en_ligne", "retourne"].includes(a.statut)
              }
            >
              {publication.isPending ? <Loader2 className="animate-spin" /> : <Rocket />}
              Marquer comme publié
            </Button>
          </section>
        </div>
      </div>
    </div>
  );
}
