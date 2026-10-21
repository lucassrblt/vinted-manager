import { describe, expect, it } from "vitest";

import { repartirRemise } from "@/components/stock/dialog-batch";
import { formatCoefficient, formatDate, formatDelai, formatEuros, saisieVersDecimal } from "@/lib/format";

// Intl insère des espaces insécables : on les normalise pour comparer.
const n = (s: string) => s.replace(/[  ]/g, " ");

describe("formats français", () => {
  it("affiche les montants en euros", () => {
    expect(n(formatEuros("1234.5"))).toBe("1 234,50 €");
    expect(formatEuros(null)).toBe("—");
  });
  it("affiche les dates JJ/MM/AAAA à l'heure de Paris", () => {
    expect(formatDate("2026-10-02")).toBe("02/10/2026");
    // 23h30 UTC le 30/09 = 01h30 le 01/10 à Paris
    expect(formatDate("2026-09-30T23:30:00Z")).toBe("01/10/2026");
  });
  it("formate coefficients et délais", () => {
    expect(formatCoefficient("3.129")).toBe("×3,13");
    expect(formatDelai(5)).toBe("5 h");
    expect(formatDelai(54)).toBe("2,3 j");
  });
  it("convertit la saisie française", () => {
    expect(saisieVersDecimal("12,50 €")).toBe("12.50");
    expect(saisieVersDecimal("abc")).toBeNull();
    expect(saisieVersDecimal("")).toBeNull();
  });
});

describe("répartition de la remise (aperçu)", () => {
  it("donne exactement la remise globale, au prorata", () => {
    const bruts = [...Array(8).fill(17.64), ...Array(4).fill(7.85), ...Array(4).fill(4.98)];
    const r = repartirRemise(bruts, 10.56);
    expect(Math.round(r.reduce((a, b) => a + b, 0) * 100)).toBe(1056);
    expect(r[0]).toBeGreaterThanOrEqual(0.97);
    expect(r[15]).toBeLessThanOrEqual(0.28);
  });
  it("ignore une remise supérieure au total", () => {
    expect(repartirRemise([10], 20)).toEqual([0]);
  });
});
