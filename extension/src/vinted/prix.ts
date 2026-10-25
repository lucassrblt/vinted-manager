/**
 * Baisse de prix (section 10.2) : `PUT /api/v2/item_upload/items/{id}` exige l'objet `item` complet.
 * L'annonce est relue (`GET /api/v2/items/{id}`) et l'objet reconstruit ; s'il manque un champ
 * nécessaire, rien n'est envoyé (un objet partiel risquerait d'effacer des champs).
 */
import { uuid } from "../outils";
import type { ClientVinted } from "./client";
import { verifierCompte } from "./compte";
import { ErreurAction } from "./erreurs";

// Champs toujours nuls dans les captures pour des vêtements : pris tels quels s'ils sont présents, nuls sinon.
const NULS_POSSIBLES = ["isbn", "measurement_length", "measurement_width", "manufacturer", "manufacturer_labelling"];

type Objet = Record<string, unknown>;

function objet(v: unknown): Objet | null {
  return typeof v === "object" && v !== null && !Array.isArray(v) ? (v as Objet) : null;
}

function nombre(v: unknown): number | null {
  const n = typeof v === "string" && v.trim() !== "" ? Number(v) : v;
  return typeof n === "number" && Number.isFinite(n) ? n : null;
}

function texte(v: unknown): string | null {
  return typeof v === "string" && v.trim() !== "" ? v : null;
}

export function prixLu(item: Objet): number | null {
  const prix = item.price;
  return nombre(objet(prix)?.amount ?? prix);
}

/** Objet `item` complet pour le PUT, à partir de l'annonce lue. Lève ErreurAction s'il manque un champ. */
export function reconstruireItem(item: Objet, nouveauPrix: string, aiPhoto: boolean | null, tempUuid: string): Objet {
  const manquants: string[] = [];
  const requis = <T>(nom: string, valeur: T | null | undefined): T | null => {
    if (valeur === null || valeur === undefined) manquants.push(nom);
    return valeur ?? null;
  };
  const marque = objet(item.brand_dto);
  const couleurs = Array.isArray(item.color_ids)
    ? item.color_ids.map(nombre).filter((n): n is number => n !== null)
    : "color1_id" in item
      ? [nombre(item.color1_id), nombre(item.color2_id)].filter((n): n is number => n !== null)
      : null;
  const photos = Array.isArray(item.photos)
    ? item.photos
        .map(objet)
        .filter((p): p is Objet => p !== null && nombre(p.id) !== null)
        .map((p) => ({ id: nombre(p.id) as number, orientation: nombre(p.orientation) ?? 0 }))
    : [];
  const attributs = Array.isArray(item.item_attributes)
    ? item.item_attributes
        .map(objet)
        .filter((a): a is Objet => a !== null && typeof a.code === "string" && Array.isArray(a.ids))
        .map((a) => ({ code: a.code as string, ids: (a.ids as unknown[]).map(nombre).filter((n) => n !== null) }))
    : [];
  const resultat: Objet = {
    id: requis("id", nombre(item.id)),
    currency: requis("currency", texte(item.currency) ?? texte(objet(item.price)?.currency_code)),
    temp_uuid: tempUuid,
    title: requis("title", texte(item.title)),
    description: requis("description", texte(item.description)),
    brand_id: requis("brand_id", nombre(item.brand_id ?? marque?.id)),
    brand: requis("brand", texte(marque?.title) ?? texte(item.brand_title) ?? texte(item.brand)),
    catalog_id: requis("catalog_id", nombre(item.catalog_id)),
    ai_photo: requis("ai_photo", aiPhoto ?? (typeof item.ai_photo === "boolean" ? item.ai_photo : null)),
    price: nouveauPrix,
    package_size_id: requis("package_size_id", nombre(item.package_size_id)),
    shipment_prices: objet(item.shipment_prices) ?? { domestic: null, international: null },
    color_ids: requis("color_ids", couleurs),
    assigned_photos: requis("photos", photos.length ? photos : null),
    item_attributes: requis("item_attributes", attributs.length ? attributs : null),
  };
  for (const cle of NULS_POSSIBLES) resultat[cle] = cle in item ? item[cle] : null;
  if (manquants.length) {
    throw new ErreurAction(`Champ manquant dans l'annonce lue : ${manquants.join(", ")}.`);
  }
  return resultat;
}

export async function modifierPrix(
  p: Record<string, unknown>,
  e: { client: ClientVinted; vintedUserId: number | null },
): Promise<Record<string, unknown>> {
  await verifierCompte(e.client, e.vintedUserId);
  const itemId = nombre(p.item_id);
  const nouveau = texte(p.nouveau_prix);
  const attendu = nombre(p.prix_actuel);
  if (itemId === null || nouveau === null || attendu === null) throw new ErreurAction("Tâche de prix incomplète.");
  const { item } = await e.client.lireArticle(itemId);
  const lu = objet(item);
  if (!lu) throw new ErreurAction("Champ manquant dans l'annonce lue : item.");
  if (lu.is_closed || lu.is_reserved || lu.item_closing_action) {
    throw new ErreurAction("Annonce vendue, réservée ou fermée : prix non modifié.");
  }
  const actuel = prixLu(lu);
  if (actuel === null) throw new ErreurAction("Champ manquant dans l'annonce lue : price.");
  if (Math.abs(actuel - attendu) > 0.001) {
    throw new ErreurAction(
      `Prix modifié entre-temps sur Vinted (${actuel} € au lieu de ${attendu} €) : rien n'est changé.`,
    );
  }
  const session = uuid();
  const complet = reconstruireItem(lu, nouveau, typeof p.ai_photo === "boolean" ? p.ai_photo : null, session);
  const r = await e.client.modifierArticle(complet, session);
  return { item_id: r?.item?.id ?? itemId, prix: nouveau };
}
