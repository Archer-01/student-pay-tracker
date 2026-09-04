import { describe, expect, it, vi } from "vitest";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test/render";
import { Modal } from "./Modal";

function Form() {
  return (
    <form>
      <label htmlFor="a">First</label>
      <input id="a" />
      <label htmlFor="b">Second</label>
      <input id="b" />
      <button type="submit">Save</button>
    </form>
  );
}

/** A realistic host: a trigger that opens the dialog, so focus restoration has somewhere to go. */
function Host({ onClose }: { onClose?: () => void } = {}) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button onClick={() => setOpen(true)}>Open</button>
      {open && (
        <Modal
          title="Record a payment"
          onClose={() => {
            setOpen(false);
            onClose?.();
          }}
        >
          <Form />
        </Modal>
      )}
    </>
  );
}

describe("Modal focus handling", () => {
  it("names itself to assistive technology using its visible heading", () => {
    renderWithProviders(
      <Modal title="Record a payment" onClose={vi.fn()}>
        <Form />
      </Modal>,
    );
    expect(screen.getByRole("dialog", { name: "Record a payment" })).toBeInTheDocument();
  });

  it("moves focus to the first field rather than leaving it behind the overlay", async () => {
    renderWithProviders(<Host />);
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    await waitFor(() => expect(screen.getByLabelText("First")).toHaveFocus());
  });

  it("focuses the panel itself when there is nothing to fill in", async () => {
    renderWithProviders(
      <Modal title="Notice" onClose={vi.fn()}>
        <p>Nothing to do here.</p>
      </Modal>,
    );
    await waitFor(() => expect(screen.getByRole("dialog")).toHaveFocus());
  });

  it("wraps Tab from the last control back to the first", async () => {
    renderWithProviders(<Host />);
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    await waitFor(() => expect(screen.getByLabelText("First")).toHaveFocus());

    // Close button is first in DOM order, so the cycle is: × → First → Second → Save → ×
    await userEvent.tab(); // Second
    await userEvent.tab(); // Save
    await userEvent.tab(); // wraps
    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
  });

  it("wraps Shift+Tab from the first control to the last", async () => {
    renderWithProviders(<Host />);
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    await waitFor(() => expect(screen.getByLabelText("First")).toHaveFocus());

    await userEvent.tab({ shift: true }); // back to the close button, still inside
    expect(screen.getByRole("button", { name: "Close" })).toHaveFocus();
    await userEvent.tab({ shift: true }); // wraps to the end rather than escaping
    expect(screen.getByRole("button", { name: "Save" })).toHaveFocus();
  });

  it("never lets focus reach the page behind it", async () => {
    renderWithProviders(<Host />);
    const opener = screen.getByRole("button", { name: "Open" });
    await userEvent.click(opener);
    await waitFor(() => expect(screen.getByLabelText("First")).toHaveFocus());

    for (let i = 0; i < 8; i++) await userEvent.tab();
    expect(opener).not.toHaveFocus();
    expect(screen.getByRole("dialog")).toContainElement(document.activeElement as HTMLElement);
  });

  it("gives focus back to whatever opened it", async () => {
    renderWithProviders(<Host />);
    const opener = screen.getByRole("button", { name: "Open" });
    await userEvent.click(opener);
    await waitFor(() => expect(screen.getByLabelText("First")).toHaveFocus());

    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(opener).toHaveFocus());
  });

  it("closes on Escape", async () => {
    const onClose = vi.fn();
    renderWithProviders(<Host onClose={onClose} />);
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    await userEvent.keyboard("{Escape}");
    expect(onClose).toHaveBeenCalled();
  });

  it("closes on a backdrop click but not on a click inside", async () => {
    const onClose = vi.fn();
    renderWithProviders(<Host onClose={onClose} />);
    await userEvent.click(screen.getByRole("button", { name: "Open" }));

    await userEvent.click(screen.getByRole("dialog"));
    expect(onClose).not.toHaveBeenCalled();

    await userEvent.click(screen.getByRole("presentation"));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("locks the page behind it from scrolling, and releases it after", async () => {
    renderWithProviders(<Host />);
    await userEvent.click(screen.getByRole("button", { name: "Open" }));
    await waitFor(() => expect(document.body.style.overflow).toBe("hidden"));

    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => expect(document.body.style.overflow).not.toBe("hidden"));
  });
});
