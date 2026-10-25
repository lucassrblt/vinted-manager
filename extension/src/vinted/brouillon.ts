/**
 * Création d'un brouillon Vinted (section 13.2 de la spécification), étape par étape, comme le site.
 * Lucas relit puis publie lui-même le brouillon.
 */
import { type Attendre, entre, uuid } from "../outils";
import type { ClientVinted, Marque, ObjetBrouillon, PhotoAssignee } from "./client";
import { verifierCompte } from "./compte";
import {
  attribut,
  choisirCouleurs,
  choisirMarque,
  choisirMatieres,
  trouverTaille,
  verifierEtat,
} from "./correspondances";
import { ErreurAction } from "./erreurs";

export interface PhotoCharge {
  photo_id: number;
  type: string;
}

/** Charge utile de `GET /api/extension/brouillons/suivant`. */
export interface ChargeBrouillon {
  article_id: number;
  titre: string;
  description: string;
  prix: string;
  marque: string | null;
  taille: string | null;
  condition_id: number;
  couleur: string | null;
  matiere: string | null;
  categorie: string | null;
  package_size_id: number;
  ai_photo: boolean;
  photos: PhotoCharge[];
}

export interface Dependances {
  client: ClientVinted;
  /** JPEG de la photo, tel que fourni par le backend (via le service worker). */
  photo: (photoId: number) => Promise<Blob>;
  attendre: Attendre;
  aleatoire?: () => number;
  /** Identifiant Vinted attendu pour ce compte. */
  vintedUserId: number | null;
  session?: string;
}

export interface PhotosEnvoyees {
  session: string;
  assignees: PhotoAssignee[];
  imageIds: string[];
}

/** Envoie les photos une par une (2 à 5 s entre chaque), dans l'ordre. */
export async function envoyerPhotos(ids: number[], d: Dependances): Promise<PhotosEnvoyees> {
  const session = d.session ?? uuid();
  const assignees: PhotoAssignee[] = [];
  const imageIds: string[] = [];
  for (const [i, id] of ids.entries()) {
    if (i > 0) await d.attendre(entre(2000, 5000, d.aleatoire));
    const envoyee = await d.client.envoyerPhoto(await d.photo(id), session);
    assignees.push({ id: envoyee.id, orientation: 0, ai_detected: false, digital_source_type: [], c2pa_read_error: "other" });
    imageIds.push(envoyee.image_uuid);
  }
  return { session, assignees, imageIds };
}

export interface Annonce {
  titre: string;
  description: string;
  prix: string;
  marque: string | null;
  taille: string | null;
  condition_id: number;
  couleur: string | null;
  matiere: string | null;
  package_size_id: number;
  ai_photo: boolean;
}

/** Catégorie, attributs et suggestions, puis l'objet `draft` complet. */
export async function preparerObjet(annonce: Annonce, photos: PhotosEnvoyees, d: Dependances): Promise<ObjetBrouillon> {
  const { client } = d;
  const categories = await client.suggestionsCategories(photos.imageIds, photos.session);
  const catalogId = categories.prefill_categories?.[0];
  if (!catalogId) throw new ErreurAction("Catégorie introuvable : Vinted n'a proposé aucune catégorie pour ces photos.");
  const { attributes } = await client.attributs(catalogId);
  const tailleId = trouverTaille(attributes, annonce.taille);
  const etatId = verifierEtat(attributes, annonce.condition_id);
  const geres = new Set(["brand", "size", "condition", "color", "material", "measurements", "category"]);
  const inconnu = attributes.find((a) => a.configuration?.required && !geres.has(a.code));
  if (inconnu) throw new ErreurAction(`Attribut obligatoire non géré par l'extension : « ${inconnu.code} ».`);

  const suggestions = await client.suggestionsAttributs({
    titre: annonce.titre,
    description: annonce.description,
    catalogId,
    imageIds: photos.imageIds,
    session: photos.session,
  });
  let listeMarques: Marque[] | null = null;
  const cible = annonce.marque?.toLowerCase();
  if (cible && !(suggestions.brands ?? []).some((b) => b.title.toLowerCase() === cible)) {
    listeMarques = (await client.marques(catalogId)).brands;
  }
  const marque = choisirMarque(annonce.marque, suggestions, listeMarques);
  const couleursVinted = suggestions.colors?.length ? null : (await client.couleurs()).colors;
  const couleurs = choisirCouleurs(annonce.couleur, suggestions, couleursVinted ?? suggestions.colors ?? []);
  const matieres = choisirMatieres(annonce.matiere, suggestions, attributes);

  const itemAttributes = [
    { code: "size", ids: [tailleId] },
    { code: "condition", ids: [etatId] },
  ];
  if (matieres.length && attribut(attributes, "material")) itemAttributes.push({ code: "material", ids: matieres });
  return {
    id: null,
    currency: "EUR",
    temp_uuid: photos.session,
    title: annonce.titre,
    description: annonce.description,
    brand_id: marque.id,
    brand: marque.title,
    catalog_id: catalogId,
    isbn: null,
    ai_photo: annonce.ai_photo,
    price: annonce.prix,
    package_size_id: annonce.package_size_id,
    shipment_prices: { domestic: null, international: null },
    color_ids: couleurs,
    assigned_photos: photos.assignees,
    measurement_length: null,
    measurement_width: null,
    item_attributes: itemAttributes,
    manufacturer: null,
    manufacturer_labelling: null,
  };
}

export interface ResultatBrouillon {
  vinted_draft_id: number;
  ai_photo: boolean;
  catalog_id: number;
  marque: string;
}

export async function creerBrouillon(charge: ChargeBrouillon, d: Dependances): Promise<ResultatBrouillon> {
  await verifierCompte(d.client, d.vintedUserId);
  if (!charge.photos.length) throw new ErreurAction("Aucune photo fournie.");
  const photos = await envoyerPhotos(
    charge.photos.map((p) => p.photo_id),
    d,
  );
  const objet = await preparerObjet(charge, photos, d);
  const reponse = await d.client.creerBrouillon(objet, photos.session);
  const id = Number(reponse?.draft?.id);
  if (!Number.isFinite(id) || id <= 0) throw new ErreurAction("Vinted n'a pas renvoyé l'identifiant du brouillon.");
  return { vinted_draft_id: id, ai_photo: objet.ai_photo, catalog_id: objet.catalog_id, marque: objet.brand };
}
