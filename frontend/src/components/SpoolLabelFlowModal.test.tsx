import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { UserSpool, UserSpoolQrIdentity } from "../api/client";
import { SpoolLabelFlowModal } from "./SpoolLabelFlowModal";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  issue: vi.fn(),
  retire: vi.fn(),
  restore: vi.fn(),
  rotate: vi.fn(),
  success: vi.fn(),
}));

vi.mock("../api/client", () => ({
  spoolQrAPI: {
    get: mocks.get,
    issue: mocks.issue,
    retire: mocks.retire,
    restore: mocks.restore,
    rotate: mocks.rotate,
  },
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key} ${JSON.stringify(options)}` : key,
  }),
}));
vi.mock("./Toast", () => ({ toast: { success: mocks.success } }));
vi.mock("./LabelStudioModal", () => ({
  LabelStudioModal: ({
    filamentId,
    spoolId,
    onClose,
  }: {
    filamentId?: number;
    spoolId?: number;
    onClose: () => void;
  }) => (
    <div role="dialog" aria-label="studio">
      {filamentId ? `product-${filamentId}` : `instance-${spoolId}`}
      <button type="button" onClick={onClose}>studio-close</button>
    </div>
  ),
}));

const spool: Pick<UserSpool, "id" | "filament_id" | "filament"> = {
  id: 101,
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

const activeIdentity: UserSpoolQrIdentity = {
  spool_id: 101,
  filament_id: 41,
  issuer: "user",
  state: "active",
  revision: 3,
  short_code: "FHQ1-instance",
  target_url: "https://example.test/qr/FHQ1-instance",
  retirement_started_at: null,
  purge_after: null,
};

function open() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <SpoolLabelFlowModal spool={spool} onClose={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe("SpoolLabelFlowModal", () => {
  beforeEach(() => {
    vi.resetAllMocks();
    sessionStorage.clear();
  });

  it("keeps product printing read-only and issues an instance only after confirmation", async () => {
    mocks.get.mockRejectedValue({ isAxiosError: true, response: { status: 404 } });
    mocks.issue.mockResolvedValue(activeIdentity);
    open();

    fireEvent.click(await screen.findByRole("button", { name: "spoolQr.printProduct" }));
    expect(screen.getByRole("dialog", { name: "studio" })).toHaveTextContent("product-41");
    expect(mocks.issue).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "studio-close" }));

    fireEvent.click(await screen.findByRole("button", { name: "spoolQr.issue" }));
    expect(mocks.issue).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "spoolQr.issueConfirm" }));
    await waitFor(() => expect(mocks.issue).toHaveBeenCalledWith(101));
    expect(await screen.findByRole("dialog", { name: "studio" })).toHaveTextContent(
      "instance-101",
    );
  });

  it("reprints the same active identity without issuing and rotates only after confirmation", async () => {
    mocks.get.mockResolvedValue(activeIdentity);
    mocks.rotate.mockResolvedValue({
      ...activeIdentity,
      revision: 4,
      short_code: "FHQ1-replacement",
    });
    open();

    fireEvent.click(
      await screen.findByRole("button", { name: "spoolQr.printInstance" }),
    );
    expect(screen.getByRole("dialog", { name: "studio" })).toHaveTextContent("instance-101");
    expect(mocks.issue).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "studio-close" }));

    fireEvent.click(screen.getByRole("button", { name: "spoolQr.rotate" }));
    expect(mocks.rotate).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "spoolQr.rotateConfirm" }));
    await waitFor(() =>
      expect(mocks.rotate).toHaveBeenCalledWith(
        101,
        3,
        expect.stringMatching(/^spool-qr-rotate-/),
      ),
    );
    expect(await screen.findByRole("dialog", { name: "studio" })).toHaveTextContent(
      "instance-101",
    );
  });

  it("blocks retired printing, restores the same identity and protects manufacturer codes", async () => {
    const pending: UserSpoolQrIdentity = {
      ...activeIdentity,
      state: "pending_retirement",
      revision: 4,
      retirement_started_at: "2026-09-01T00:00:00Z",
      purge_after: "2026-09-08T00:00:00Z",
    };
    mocks.get.mockResolvedValue(pending);
    mocks.restore.mockResolvedValue({ ...activeIdentity, revision: 5 });
    const view = open();

    expect(
      await screen.findByRole("button", { name: "spoolQr.restore" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "spoolQr.printInstance" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "spoolQr.restore" }));
    await waitFor(() => expect(mocks.restore).toHaveBeenCalledWith(101, 4));
    expect(
      await screen.findByRole("button", { name: "spoolQr.printInstance" }),
    ).toBeInTheDocument();

    view.unmount();
    mocks.get.mockResolvedValue({
      ...activeIdentity,
      issuer: "manufacturer",
      state: "linked",
    });
    open();
    expect(
      await screen.findByRole("button", { name: "spoolQr.printInstance" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "spoolQr.rotate" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "spoolQr.retire" })).not.toBeInTheDocument();
  });
});
