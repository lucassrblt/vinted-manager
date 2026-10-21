"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { formatEuros } from "@/lib/format";

// Couleurs validées (daltonisme + contraste) dans globals.css : --chart-1 (CA), --chart-2 (marge).
const AXE = { fontSize: 11, fill: "var(--muted-foreground)" };

function InfoBulle({
  active,
  payload,
  label,
  format,
}: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
  label?: string;
  format: (v: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border bg-popover px-3 py-2 text-xs shadow-md">
      <p className="mb-1 font-medium">{label}</p>
      {payload.map((p) => (
        <p key={p.name} className="flex items-center gap-2 tabular-nums">
          <span className="size-2 rounded-sm" style={{ background: p.color }} />
          <span className="text-muted-foreground">{p.name}</span>
          <span className="ml-auto font-medium">{format(p.value)}</span>
        </p>
      ))}
    </div>
  );
}

export function Legende({ series }: { series: { libelle: string; couleur: string }[] }) {
  return (
    <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
      {series.map((s) => (
        <span key={s.libelle} className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm" style={{ background: s.couleur }} />
          {s.libelle}
        </span>
      ))}
    </div>
  );
}

/** Barres groupées CA / marge par période (une seule échelle, en euros). */
export function GraphiqueCaMarge({ donnees }: { donnees: { periode: string; ca: number; marge: number }[] }) {
  return (
    <div className="h-64 w-full" role="img" aria-label="Chiffre d'affaires et marge par période">
      <ResponsiveContainer>
        <BarChart data={donnees} barGap={2} margin={{ top: 8, right: 4, left: 4, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis dataKey="periode" tickLine={false} axisLine={false} tick={AXE} />
          <YAxis tickLine={false} axisLine={false} tick={AXE} width={48} tickFormatter={(v) => `${v} €`} />
          <Tooltip cursor={{ fill: "var(--muted)", opacity: 0.5 }} content={<InfoBulle format={formatEuros} />} />
          <Bar dataKey="ca" name="CA" fill="var(--chart-1)" radius={[4, 4, 0, 0]} maxBarSize={28} />
          <Bar dataKey="marge" name="Marge" fill="var(--chart-2)" radius={[4, 4, 0, 0]} maxBarSize={28} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Barres horizontales à une série (répartition par marque, catégorie…). */
export function BarresHorizontales({
  donnees,
  format,
  libelleSerie,
}: {
  donnees: { cle: string; valeur: number }[];
  format: (v: number) => string;
  libelleSerie: string;
}) {
  const hauteur = Math.max(120, donnees.length * 30 + 20);
  return (
    <div style={{ height: hauteur }} className="w-full" role="img" aria-label={libelleSerie}>
      <ResponsiveContainer>
        <BarChart data={donnees} layout="vertical" margin={{ top: 0, right: 56, left: 0, bottom: 0 }}>
          <XAxis type="number" hide />
          <YAxis type="category" dataKey="cle" tickLine={false} axisLine={false} tick={AXE} width={130} />
          <Tooltip cursor={{ fill: "var(--muted)", opacity: 0.5 }} content={<InfoBulle format={format} />} />
          <Bar
            dataKey="valeur"
            name={libelleSerie}
            fill="var(--chart-1)"
            radius={[0, 4, 4, 0]}
            barSize={16}
            label={{
              position: "right",
              fontSize: 11,
              fill: "var(--muted-foreground)",
              formatter: (v: unknown) => format(Number(v)),
            }}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
