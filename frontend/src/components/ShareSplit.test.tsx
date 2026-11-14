import { describe, expect, it } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../test/render";
import { ShareSplit } from "./ShareSplit";

describe("ShareSplit", () => {
  it("shows what is yours and what goes to the school, with the rate", () => {
    renderWithProviders(<ShareSplit share={{ percent: "25", school: "390.00", teacher: "1170.00" }} />);
    expect(screen.getByText("Your share")).toBeInTheDocument();
    expect(screen.getByText("1,170 DH")).toBeInTheDocument();
    expect(screen.getByText("School's share (25%)")).toBeInTheDocument();
    expect(screen.getByText("390 DH")).toBeInTheDocument();
  });

  it("disappears when there is no share to give", () => {
    const { container } = renderWithProviders(
      <ShareSplit share={{ percent: "0", school: "0.00", teacher: "1560.00" }} />,
    );
    expect(container).toBeEmptyDOMElement();
  });
});
