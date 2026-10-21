"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api } from "@/lib/api";
import type { Article, BatchStats, Page, Parametres, Statut } from "@/lib/types";

export interface FiltresStock {
  statut?: Statut[];
  batch_id?: number[];
  marque?: string[];
  categorie?: string[];
  taille?: string[];
  q?: string;
  tri?: string;
  ordre?: "asc" | "desc";
  page?: number;
  taille_page?: number;
}

export function useArticles(filtres: FiltresStock) {
  return useQuery({
    queryKey: ["articles", filtres],
    queryFn: () => api<Page<Article>>("/articles", { params: { ...filtres } }),
    placeholderData: (precedent) => precedent,
  });
}

export function useArticle(id: number) {
  return useQuery({ queryKey: ["article", id], queryFn: () => api<Article>(`/articles/${id}`) });
}

export function useValeursFiltres() {
  return useQuery({
    queryKey: ["articles", "filtres"],
    queryFn: () =>
      api<{ marques: string[]; categories: string[]; tailles: string[]; sources: string[] }>("/articles/filtres"),
    staleTime: 60_000,
  });
}

export function useBatches() {
  return useQuery({ queryKey: ["batches"], queryFn: () => api<BatchStats[]>("/batches") });
}

export function useParametres() {
  return useQuery({ queryKey: ["parametres"], queryFn: () => api<Parametres>("/parametres"), staleTime: 300_000 });
}

/** Invalide tout ce qui dépend des articles (stock, batches, compta, écran du jour). */
export function useInvaliderStock() {
  const qc = useQueryClient();
  return () => {
    for (const cle of [
      "articles",
      "article",
      "batches",
      "batch",
      "compta",
      "dashboard",
      "alertes",
      "sourcing",
      "timeline",
    ]) {
      qc.invalidateQueries({ queryKey: [cle] });
    }
  };
}

export function useModifierArticle() {
  const invalider = useInvaliderStock();
  return useMutation({
    mutationFn: ({ id, ...champs }: { id: number } & Partial<Record<string, unknown>>) =>
      api<Article>(`/articles/${id}`, { method: "PATCH", body: champs }),
    onSuccess: () => invalider(),
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useChangerStatut() {
  const invalider = useInvaliderStock();
  return useMutation({
    mutationFn: ({ id, statut }: { id: number; statut: Statut }) =>
      api<Article>(`/articles/${id}/statut`, { body: { statut } }),
    onSuccess: () => invalider(),
    onError: (e: Error) => toast.error(e.message),
  });
}

export function useActionGroupee() {
  const invalider = useInvaliderStock();
  return useMutation({
    mutationFn: (corps: { ids: number[]; action: string; statut?: Statut; batch_id?: number | null }) =>
      api<{ modifies: number }>("/articles/bulk", { body: corps }),
    onSuccess: () => invalider(),
    onError: (e: Error) => toast.error(e.message),
  });
}
