import type { Metadata, Viewport } from "next";
import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";

import { Providers } from "@/components/providers";

import "./globals.css";

export const metadata: Metadata = {
  title: { default: "Revente", template: "%s · Revente" },
  description: "Gestion de la revente Vinted : stock, ventes, envois, compta.",
  manifest: "/manifest.webmanifest",
  applicationName: "Revente",
  appleWebApp: { capable: true, title: "Revente", statusBarStyle: "default" },
  icons: {
    icon: [
      { url: "/icons/favicon-32.png", sizes: "32x32" },
      { url: "/icons/icon-192.png", sizes: "192x192" },
    ],
    apple: "/icons/apple-touch-icon.png",
  },
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#fcfcfc" },
    { media: "(prefers-color-scheme: dark)", color: "#18181b" },
  ],
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="fr" suppressHydrationWarning className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="antialiased">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
