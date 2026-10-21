import { toast } from "sonner";

export async function copier(texte: string, libelle = "Texte"): Promise<void> {
  try {
    await navigator.clipboard.writeText(texte);
    toast.success(`${libelle} copié`);
  } catch {
    toast.error("Copie impossible : sélectionne le texte et copie-le à la main.");
  }
}
