"use client";

import { Loader2, Shirt } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, ApiError } from "@/lib/api";

function FormulaireConnexion() {
  const router = useRouter();
  const suite = useSearchParams().get("suite");
  const [email, setEmail] = useState("");
  const [motDePasse, setMotDePasse] = useState("");
  const [erreur, setErreur] = useState<string | null>(null);
  const [envoi, setEnvoi] = useState(false);

  async function connexion(e: React.FormEvent) {
    e.preventDefault();
    setErreur(null);
    setEnvoi(true);
    try {
      await api("/auth/login", { body: { email, mot_de_passe: motDePasse } });
      // Seuls les chemins internes sont acceptés comme destination de retour.
      router.replace(suite?.startsWith("/") && !suite.startsWith("//") ? suite : "/");
      router.refresh();
    } catch (err) {
      setErreur(err instanceof ApiError ? err.message : "Connexion impossible.");
      setEnvoi(false);
    }
  }

  return (
    <form onSubmit={connexion} className="space-y-4" noValidate>
      <div className="space-y-1.5">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          autoComplete="username"
          autoFocus
          required
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="h-10"
        />
      </div>
      <div className="space-y-1.5">
        <Label htmlFor="mot-de-passe">Mot de passe</Label>
        <Input
          id="mot-de-passe"
          type="password"
          autoComplete="current-password"
          required
          value={motDePasse}
          onChange={(e) => setMotDePasse(e.target.value)}
          className="h-10"
        />
      </div>
      {erreur && (
        <p role="alert" className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
          {erreur}
        </p>
      )}
      <Button
        type="submit"
        className="h-10 w-full bg-brand text-brand-foreground hover:bg-brand/90"
        disabled={envoi || !email || !motDePasse}
      >
        {envoi && <Loader2 className="animate-spin" />}
        Se connecter
      </Button>
    </form>
  );
}

export default function PageLogin() {
  return (
    <main className="relative flex min-h-dvh items-center justify-center overflow-hidden px-4">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(60rem_30rem_at_50%_-10%,var(--brand-soft),transparent)]"
      />
      <div className="relative w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-3 text-center">
          <div className="flex size-11 items-center justify-center rounded-xl bg-brand text-brand-foreground shadow-sm">
            <Shirt className="size-5" />
          </div>
          <div>
            <h1 className="text-xl font-semibold tracking-tight">Revente</h1>
            <p className="text-sm text-muted-foreground">Stock, ventes et envois Vinted</p>
          </div>
        </div>
        <div className="rounded-xl border bg-card p-6 shadow-[0_1px_2px_rgba(0,0,0,0.04)]">
          <Suspense>
            <FormulaireConnexion />
          </Suspense>
        </div>
      </div>
    </main>
  );
}
