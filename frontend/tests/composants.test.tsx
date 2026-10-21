import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { IndicateurBadge, StatutBadge } from "@/components/commun";
import { CelluleEditable } from "@/components/stock/cellule-editable";

describe("badges", () => {
  it("affiche le libellé du statut", () => {
    render(<StatutBadge statut="recu_a_publier" />);
    expect(screen.getByText("Reçu · à publier")).toBeInTheDocument();
  });
  it("n'affiche rien sans indicateur", () => {
    const { container } = render(<IndicateurBadge indicateur={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("cellule éditable", () => {
  it("enregistre un montant saisi à la française", () => {
    const onSave = vi.fn();
    render(<CelluleEditable type="montant" libelle="le prix" valeur="10.00" onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: "Modifier le prix" }));
    const champ = screen.getByRole("textbox", { name: "le prix" });
    fireEvent.change(champ, { target: { value: "12,5" } });
    fireEvent.keyDown(champ, { key: "Enter" });
    expect(onSave).toHaveBeenCalledWith("12.5");
  });
  it("refuse un montant invalide sans enregistrer", () => {
    const onSave = vi.fn();
    render(<CelluleEditable type="montant" libelle="le prix" valeur="10.00" onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: "Modifier le prix" }));
    const champ = screen.getByRole("textbox", { name: "le prix" });
    fireEvent.change(champ, { target: { value: "dix" } });
    fireEvent.keyDown(champ, { key: "Enter" });
    expect(onSave).not.toHaveBeenCalled();
    expect(champ).toHaveAttribute("aria-invalid", "true");
  });
  it("n'enregistre pas si la valeur n'a pas changé", () => {
    const onSave = vi.fn();
    render(<CelluleEditable type="montant" libelle="le prix" valeur="10.00" onSave={onSave} />);
    fireEvent.click(screen.getByRole("button", { name: "Modifier le prix" }));
    fireEvent.keyDown(screen.getByRole("textbox", { name: "le prix" }), { key: "Enter" });
    expect(onSave).not.toHaveBeenCalled();
  });
});
