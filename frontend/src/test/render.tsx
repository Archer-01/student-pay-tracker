import type { ReactElement, ReactNode } from "react";
import { render, type RenderOptions } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

/**
 * Render with the providers every screen assumes: a router (components use `Link` and
 * `useSearchParams` freely) and the real i18n singleton, wired up in `setup.ts`.
 */
export function renderWithProviders(
  ui: ReactElement,
  { route = "/", ...options }: RenderOptions & { route?: string } = {},
) {
  function Wrapper({ children }: { children: ReactNode }) {
    return <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>;
  }
  return render(ui, { wrapper: Wrapper, ...options });
}

export * from "@testing-library/react";
