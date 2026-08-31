import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { UserSpool } from "../api/client";
import { SpoolLabelButton } from "./SpoolLabelButton";

const auth = vi.hoisted(() => ({ user: { id: 7 } as { id: number } | null }));
vi.mock("../contexts/AuthContext", () => ({ useAuth: () => auth }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("./LabelStudioModal", () => ({
  LabelStudioModal: ({
    filamentId,
    onClose,
  }: {
    filamentId: number;
    onClose: () => void;
  }) => (
    <div role="dialog" aria-label="Label">
      <span>{filamentId}</span>
      <button onClick={onClose}>Close</button>
    </div>
  ),
}));
const spool: Pick<UserSpool, "id" | "user_id" | "filament_id" | "filament"> = {
  id: 101,
  user_id: 7,
  filament_id: 41,
  filament: {
    id: 41,
    name: "Deep Ocean",
    material_type: "PLA",
    color_name: null,
    color_hex: null,
    brand_name: "OlgaCraft",
    price_per_kg: null,
    currency: null,
    required_nozzle_hrc: null,
    qr_code: "FH-OCEAN",
  },
};

describe("spool label entry", () => {
  beforeEach(() => {
    auth.user = { id: 7 };
  });
  it.each([false, true])(
    "opens the shared editor for the catalog product, not the spool id (compact=%s)",
    (compact) => {
      render(<SpoolLabelButton spool={spool} compact={compact} />);
      if (compact) {
        expect(screen.queryByText("labelStudio.labelAction")).not.toBeInTheDocument();
      } else {
        expect(screen.getByText("labelStudio.labelAction")).toBeInTheDocument();
      }
      fireEvent.click(
        screen.getByRole("button", { name: "labelStudio.printLabel" }),
      );
      expect(screen.getByRole("dialog")).toHaveTextContent("41");
      expect(screen.getByRole("dialog")).not.toHaveTextContent("101");
      fireEvent.click(screen.getByText("Close"));
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    },
  );
  it("does not print foreign spools or offer a code for an unmatched or QR-less material", () => {
    const { rerender } = render(
      <SpoolLabelButton spool={{ ...spool, user_id: 8 }} />,
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    for (const unavailable of [
      { ...spool, filament_id: null, filament: null },
      { ...spool, filament: { ...spool.filament!, qr_code: null } },
    ]) {
      rerender(<SpoolLabelButton spool={unavailable} />);
      expect(screen.getByRole("button")).toBeDisabled();
      expect(screen.getByRole("button")).toHaveAttribute(
        "title",
        "labelStudio.spoolUnavailable",
      );
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    }
    auth.user = null;
    rerender(<SpoolLabelButton spool={spool} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
