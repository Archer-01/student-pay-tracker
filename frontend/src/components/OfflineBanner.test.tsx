import { afterEach, describe, expect, it } from "vitest";
import { act, screen } from "@testing-library/react";
import { renderWithProviders } from "../test/render";
import { reportOffline, reportStored, resetConnectivity } from "../lib/connectivity";
import { OfflineBanner } from "./OfflineBanner";

afterEach(() => resetConnectivity());

describe("OfflineBanner", () => {
  it("stays out of the way while online", () => {
    const { container } = renderWithProviders(<OfflineBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it("says the data is a stored copy, read only, and how old it is", () => {
    renderWithProviders(<OfflineBanner />);
    act(() => reportStored("2026-11-14T09:41:00"));
    const banner = screen.getByRole("status");
    expect(banner).toHaveTextContent(/offline · read only/i);
    expect(banner).toHaveTextContent(/Nov 14/);
    expect(banner).toHaveTextContent(/9:41/);
  });

  it("still says it's offline when nothing is stored", () => {
    renderWithProviders(<OfflineBanner />);
    act(() => reportOffline());
    expect(screen.getByRole("status")).toHaveTextContent(/offline · read only/i);
  });
});
