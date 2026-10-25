/** Lecture du dressing (toutes les pages), transmise au backend qui rattache chaque annonce à un article. */
import { type Attendre, entre } from "../outils";
import type { ArticleDressing, ClientVinted } from "./client";
import { ErreurAction } from "./erreurs";

export const PAR_PAGE = 20;
export const PAGES_MAX = 50;

export function reduireArticle(a: ArticleDressing): Record<string, unknown> {
  return {
    id: a.id,
    title: a.title,
    is_draft: a.is_draft,
    is_closed: a.is_closed ?? false,
    is_hidden: a.is_hidden ?? false,
    is_reserved: a.is_reserved ?? false,
    item_closing_action: a.item_closing_action ?? null,
    price: { amount: a.price?.amount },
    favourite_count: a.favourite_count,
    view_count: a.view_count,
    brand: a.brand,
    size: a.size,
    status: a.status,
    photos: (a.photos ?? []).map((p) => ({ id: p.id, full_size_url: p.full_size_url ?? p.url })),
  };
}

/** `complet` n'est vrai que si toutes les pages ont été lues : le backend ne conclut à une disparition
 * qu'à cette condition. */
export async function lireDressing(
  client: ClientVinted,
  userId: number | null,
  attendre: Attendre,
  aleatoire?: () => number,
): Promise<{ items: Record<string, unknown>[]; complet: boolean; total: number }> {
  if (!userId) throw new ErreurAction("Identifiant Vinted attendu inconnu : dressing non lu.");
  const items: Record<string, unknown>[] = [];
  let page = 1;
  let total = 0;
  let pages = 1;
  do {
    if (page > 1) await attendre(entre(2000, 4000, aleatoire));
    const r = await client.dressing(userId, page, PAR_PAGE);
    items.push(...(r.items ?? []).map(reduireArticle));
    total = r.pagination?.total_entries ?? items.length;
    pages = r.pagination?.total_pages ?? 1;
    page += 1;
  } while (page <= pages && page <= PAGES_MAX);
  return { items, complet: page > pages && items.length >= Math.min(total, pages * PAR_PAGE), total };
}
