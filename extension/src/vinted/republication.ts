/**
 * Republication (section 13.3) : nouveau brouillon avec les photos transformées par le backend et le
 * texte reformulé, publication (`completion`), puis suppression de l'ancienne annonce. Dans cet ordre :
 * en cas d'échec, l'ancienne annonce reste en ligne.
 */
import { type Attendre, entre } from "../outils";
import { type Annonce, envoyerPhotos, preparerObjet } from "./brouillon";
import type { ClientVinted } from "./client";
import { verifierCompte } from "./compte";
import { ErreurAction, ErreurVinted } from "./erreurs";

/** Échec après une étape déjà faite sur Vinted : le résultat partiel est transmis au backend. */
export class ErreurPartielle extends Error {
  constructor(
    public readonly cause: Error,
    public readonly partiel: Record<string, unknown>,
    message: string,
  ) {
    super(message);
    this.name = "ErreurPartielle";
  }
}

export interface ChargeRepublication extends Annonce {
  ancien_item_id: number;
  photos: { index: number }[];
}

export async function republier(
  p: ChargeRepublication,
  e: {
    client: ClientVinted;
    vintedUserId: number | null;
    photo: (index: number) => Promise<Blob>;
    attendre: Attendre;
    aleatoire?: () => number;
    session?: string;
  },
): Promise<Record<string, unknown>> {
  await verifierCompte(e.client, e.vintedUserId);
  const ancien = Number(p.ancien_item_id);
  if (!Number.isFinite(ancien) || ancien <= 0) throw new ErreurAction("Ancienne annonce inconnue.");
  const { item } = await e.client.lireArticle(ancien);
  if (!item || item.is_closed || item.is_reserved || item.is_draft || item.item_closing_action) {
    throw new ErreurAction("Annonce vendue, réservée ou fermée entre-temps : republication annulée.");
  }
  if (!p.photos.length) throw new ErreurAction("Aucune photo à publier.");
  const d = {
    client: e.client,
    photo: e.photo,
    attendre: e.attendre,
    aleatoire: e.aleatoire,
    vintedUserId: e.vintedUserId,
    session: e.session,
  };
  const photos = await envoyerPhotos(
    p.photos.map((x) => x.index),
    d,
  );
  const objet = await preparerObjet(p, photos, d);
  const brouillon = Number((await e.client.creerBrouillon(objet, photos.session))?.draft?.id);
  if (!Number.isFinite(brouillon) || brouillon <= 0)
    throw new ErreurAction("Vinted n'a pas renvoyé l'identifiant du brouillon.");
  await e.attendre(entre(3000, 8000, e.aleatoire));
  let nouvel: number;
  try {
    const publie = await e.client.publierBrouillon(
      {
        ...objet,
        id: brouillon,
        assigned_photos: objet.assigned_photos.map(({ id, orientation }) => ({ id, orientation })),
      },
      photos.session,
    );
    nouvel = Number(publie?.item?.id ?? brouillon);
  } catch (err) {
    throw new ErreurPartielle(
      err as Error,
      { brouillon_id: brouillon },
      `Brouillon ${brouillon} créé mais non publié : ${(err as Error).message}`,
    );
  }
  await e.attendre(entre(5000, 15000, e.aleatoire));
  try {
    await e.client.supprimerArticle(ancien);
  } catch (err) {
    throw new ErreurPartielle(
      err as Error,
      { nouvel_item_id: nouvel },
      `Nouvelle annonce ${nouvel} publiée, mais l'ancienne (${ancien}) n'a pas été supprimée : ${(err as Error).message}`,
    );
  }
  return { nouvel_item_id: nouvel, ancien_item_id: ancien };
}

export function estErreurVinted(e: unknown): e is ErreurVinted {
  return e instanceof ErreurVinted;
}
