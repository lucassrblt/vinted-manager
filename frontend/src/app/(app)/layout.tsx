"use client";

import { useEffect, useState } from "react";

import { Header } from "@/components/layout/header";
import { RechercheGlobale } from "@/components/layout/recherche";
import { Sidebar } from "@/components/layout/sidebar";

const CLE_REPLIE = "sidebar-repliee";

export default function LayoutApp({ children }: { children: React.ReactNode }) {
  const [replie, setReplie] = useState(false);
  const [recherche, setRecherche] = useState(false);

  useEffect(() => {
    try {
      setReplie(localStorage.getItem(CLE_REPLIE) === "1");
    } catch {
      /* stockage indisponible */
    }
  }, []);

  function basculer() {
    setReplie((r) => {
      try {
        localStorage.setItem(CLE_REPLIE, r ? "0" : "1");
      } catch {
        /* stockage indisponible */
      }
      return !r;
    });
  }

  return (
    <div className="flex min-h-dvh">
      <a
        href="#contenu"
        className="sr-only z-50 rounded-md bg-background px-3 py-2 focus:not-sr-only focus:fixed focus:top-2 focus:left-2"
      >
        Aller au contenu
      </a>
      <Sidebar replie={replie} basculer={basculer} />
      <div className="flex min-w-0 flex-1 flex-col">
        <Header ouvrirRecherche={() => setRecherche(true)} />
        <main id="contenu" className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 md:px-8 md:py-8">
          {children}
        </main>
      </div>
      <RechercheGlobale ouvert={recherche} setOuvert={setRecherche} />
    </div>
  );
}
