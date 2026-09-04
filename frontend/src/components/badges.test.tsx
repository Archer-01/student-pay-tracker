import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../test/render";
import { DriftBadge } from "./DriftBadge";
import { OverdueBadge } from "./OverdueBadge";

describe("DriftBadge", () => {
  it("says a student is on track rather than showing a bare zero", () => {
    renderWithProviders(<DriftBadge drift={0} />);
    expect(screen.getByText(/on track/i)).toBeInTheDocument();
  });

  it("uses the singular for a single day", () => {
    renderWithProviders(<DriftBadge drift={1} />);
    expect(screen.getByText(/1 day\b/i)).toBeInTheDocument();
  });

  it("uses the plural beyond one", () => {
    renderWithProviders(<DriftBadge drift={25} />);
    expect(screen.getByText(/25 days/i)).toBeInTheDocument();
  });
});

describe("OverdueBadge", () => {
  it("says paid up rather than showing a bare zero", () => {
    renderWithProviders(<OverdueBadge monthsOverdue={0} />);
    expect(screen.getByText(/paid up/i)).toBeInTheDocument();
  });

  it("uses the singular for one month", () => {
    renderWithProviders(<OverdueBadge monthsOverdue={1} />);
    expect(screen.getByText(/1 month\b/i)).toBeInTheDocument();
  });

  it("uses the plural beyond one", () => {
    renderWithProviders(<OverdueBadge monthsOverdue={13} />);
    expect(screen.getByText(/13 months/i)).toBeInTheDocument();
  });
});
