import { beforeEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test/render";
import * as endpoints from "../../api/endpoints";
import { PricingFields } from "./PricingFields";

const packs = [
  { id: 1, name: "Pack complet", level: "1AC", price: "220.00", is_active: true,
    created_at: "", subjects: ["Maths"], student_count: 0 },
  { id: 2, name: "Maths seul", level: "2BAC", price: "150.00", is_active: true,
    created_at: "", subjects: ["Maths"], student_count: 0 },
];

beforeEach(() => {
  vi.spyOn(endpoints, "listPacks").mockResolvedValue(packs as never);
});

function setup(props: Partial<Parameters<typeof PricingFields>[0]> = {}) {
  return renderWithProviders(
    <PricingFields
      packId="" onPackId={vi.fn()}
      customPrice="" onCustomPrice={vi.fn()}
      priceNote="" onPriceNote={vi.fn()}
      {...props}
    />,
  );
}

describe("PricingFields", () => {
  it("only offers packs that are still sold", async () => {
    setup();
    await waitFor(() => expect(endpoints.listPacks).toHaveBeenCalledWith({ active: true }));
  });

  it("puts packs matching the student's class level first", async () => {
    setup({ classLevel: "2BAC" });
    await waitFor(() => expect(screen.getByLabelText(/pack/i)).toBeInTheDocument());
    const options = Array.from(
      screen.getByLabelText(/pack/i).querySelectorAll("option"),
    ).map((o) => o.textContent);
    // "No pack" first, then the level that matches the student's class.
    expect(options[1]).toContain("2BAC");
  });

  it("warns when the chosen pack is for another level", async () => {
    setup({ packId: "1", classLevel: "2BAC" });
    // Advisory only: the backend allows it, so the UI must warn rather than block.
    expect(await screen.findByText(/1AC.*2BAC|2BAC.*1AC/)).toBeInTheDocument();
  });

  it("stays quiet when the levels agree", async () => {
    setup({ packId: "2", classLevel: "2BAC" });
    await waitFor(() => expect(endpoints.listPacks).toHaveBeenCalled());
    expect(screen.queryByText(/but the class is/i)).not.toBeInTheDocument();
  });

  it("stays quiet when the student has no class to compare against", async () => {
    setup({ packId: "1" });
    await waitFor(() => expect(endpoints.listPacks).toHaveBeenCalled());
    expect(screen.queryByText(/but the class is/i)).not.toBeInTheDocument();
  });

  it("hides the reason field until there is an agreed price to explain", async () => {
    const { rerender } = setup();
    await waitFor(() => expect(endpoints.listPacks).toHaveBeenCalled());
    expect(screen.queryByLabelText(/why/i)).not.toBeInTheDocument();
    rerender(
      <PricingFields
        packId="" onPackId={vi.fn()}
        customPrice="90" onCustomPrice={vi.fn()}
        priceNote="" onPriceNote={vi.fn()}
      />,
    );
    expect(screen.getByLabelText(/why/i)).toBeInTheDocument();
  });
});
