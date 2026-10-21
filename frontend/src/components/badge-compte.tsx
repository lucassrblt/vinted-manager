import { UserRound } from "lucide-react";

/** Compte Vinted concerné (affiché seulement quand plusieurs comptes sont branchés). */
export function BadgeCompte({ nom }: { nom: string | null | undefined }) {
  if (!nom) return null;
  return (
    <span className="inline-flex items-center gap-1 rounded-md bg-muted px-1.5 py-0.5 text-[11px] font-medium text-muted-foreground">
      <UserRound className="size-3" />
      {nom}
    </span>
  );
}
