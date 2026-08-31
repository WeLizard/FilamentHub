import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { LabelStudioModal } from "./LabelStudioModal";

const mocks = vi.hoisted(() => ({
  metadata: vi.fn(),
  preview: vi.fn(),
  download: vi.fn(),
  error: vi.fn(),
  decode: vi.fn(),
}));
vi.mock("../api/client", () => ({ labelsAPI: mocks }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "ru" } }),
}));
vi.mock("./Toast", () => ({ toast: { error: mocks.error } }));

describe("LabelStudioModal", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    let imageId = 0;
    URL.createObjectURL = vi.fn(() => `blob:label-preview-${++imageId}`);
    URL.revokeObjectURL = vi.fn();
    mocks.decode.mockResolvedValue(undefined);
    vi.stubGlobal(
      "Image",
      class {
        src = "";
        decode = mocks.decode;
      },
    );
    mocks.metadata.mockResolvedValue({
      data: {
        sku: "FH-001",
        brand: "Brand",
        name: "Graphite",
        material: "PETG",
        fields: [["nozzle", "Nozzle", "235–255 °C"]],
      },
      media_presets: [{ width_mm: 40, height_mm: 12 }],
      classic_presets_mm: [20, 30],
      brand_logo_available: false,
    });
    mocks.preview.mockResolvedValue({
      svg: "<svg/>",
      page_svg: "<svg/>",
      modules: 33,
      scene: { dots_per_module: 4, body_size_mm: 2 },
      printable: true,
      proof_required: false,
    });
    mocks.download.mockResolvedValue(undefined);
  });
  afterEach(() => vi.unstubAllGlobals());

  function open() {
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    return render(
      <QueryClientProvider client={client}>
        <LabelStudioModal filamentId={12} onClose={vi.fn()} />
      </QueryClientProvider>,
    );
  }

  it("exports only the current preview and keeps classic mark independent from external attribution", async () => {
    open();
    const download = await screen.findByRole("button", {
      name: "labelStudio.download",
    });
    await waitFor(() => expect(download).not.toBeDisabled());
    expect(screen.getByLabelText("labelStudio.brandLogo")).toBeDisabled();
    expect(screen.getByLabelText("labelStudio.brandLogo")).not.toBeChecked();
    fireEvent.click(
      screen.getByRole("button", { name: "labelStudio.classic" }),
    );
    expect(download).toBeDisabled();
    fireEvent.click(screen.getByLabelText("labelStudio.centerMark"));
    expect(
      screen.queryByText("labelStudio.attribution"),
    ).not.toBeInTheDocument();
    await waitFor(() => expect(download).not.toBeDisabled());
    fireEvent.click(download);
    await waitFor(() =>
      expect(mocks.download).toHaveBeenCalledWith(
        12,
        expect.objectContaining({
          label: expect.objectContaining({
            kind: "classic",
            qr_mark: true,
            width_mm: 30,
            height_mm: 30,
          }),
        }),
      ),
    );
    expect(mocks.download.mock.calls[0][1].label).not.toHaveProperty("sku");
  });

  it("retains a comment when changing size but does not submit it on tiny labels", async () => {
    open();
    await screen.findByLabelText("labelStudio.width");
    expect(
      screen.queryByRole("textbox", { name: /labelStudio.comment/ }),
    ).not.toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("labelStudio.width"), {
      target: { value: "220" },
    });
    fireEvent.change(screen.getByLabelText("labelStudio.height"), {
      target: { value: "220" },
    });
    fireEvent.click(screen.getByRole("button", { name: "labelStudio.apply" }));
    const comment = screen.getByRole("textbox", {
      name: /labelStudio.comment/,
    });
    expect(comment).toHaveAttribute("maxLength", "200");
    fireEvent.change(comment, { target: { value: "Keep dry" } });
    fireEvent.click(screen.getByRole("button", { name: "40 × 12" }));
    expect(
      screen.queryByRole("textbox", { name: /labelStudio.comment/ }),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("labelStudio.commentUnavailable"),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(mocks.preview).toHaveBeenLastCalledWith(
        12,
        expect.objectContaining({
          label: expect.objectContaining({
            width_mm: 40,
            height_mm: 12,
            comment: "",
          }),
        }),
        expect.any(AbortSignal),
      ),
    );
  });

  it("keeps the decoded preview visible until its replacement is ready", async () => {
    open();
    const download = await screen.findByRole("button", {
      name: "labelStudio.download",
    });
    await waitFor(() => expect(download).not.toBeDisabled());
    const image = screen.getByAltText("labelStudio.preview");
    const original = image.getAttribute("src");
    let respond!: (value: unknown) => void;
    let decoded!: () => void;
    mocks.preview.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          respond = resolve;
        }),
    );
    mocks.decode.mockImplementationOnce(
      () =>
        new Promise<void>((resolve) => {
          decoded = resolve;
        }),
    );
    fireEvent.click(screen.getByLabelText(/Nozzle/));
    await waitFor(() => expect(mocks.preview).toHaveBeenCalledTimes(2));
    expect(screen.getByAltText("labelStudio.preview")).toBe(image);
    expect(image).toHaveAttribute("src", original);
    expect(image).not.toHaveClass("opacity-50");
    expect(download).toBeDisabled();
    await act(async () =>
      respond({
        svg: "<svg><path/></svg>",
        page_svg: "<svg/>",
        modules: 33,
        scene: { dots_per_module: 4 },
        printable: true,
      }),
    );
    await waitFor(() => expect(mocks.decode).toHaveBeenCalledTimes(2));
    expect(image).toHaveAttribute("src", original);
    expect(download).toBeDisabled();
    await act(async () => decoded());
    await waitFor(() => expect(image.getAttribute("src")).not.toBe(original));
    expect(download).not.toBeDisabled();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith(original);
  });

  it("gives micro labels the external attribution space without losing the larger-label preference", async () => {
    open();
    await screen.findByRole("button", { name: "40 × 12" });
    fireEvent.click(screen.getByRole("button", { name: "40 × 12" }));
    expect(
      screen.queryByText("labelStudio.attribution"),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("labelStudio.microAttribution"),
    ).toBeInTheDocument();
    await waitFor(() =>
      expect(mocks.preview).toHaveBeenLastCalledWith(
        12,
        expect.objectContaining({
          label: expect.objectContaining({ attribution: "none" }),
        }),
        expect.any(AbortSignal),
      ),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "labelStudio.portrait" }),
    );
    await waitFor(() =>
      expect(mocks.preview).toHaveBeenLastCalledWith(
        12,
        expect.objectContaining({
          label: expect.objectContaining({
            width_mm: 12,
            height_mm: 40,
            attribution: "none",
          }),
        }),
        expect.any(AbortSignal),
      ),
    );
    fireEvent.change(screen.getByLabelText("labelStudio.width"), {
      target: { value: "50" },
    });
    fireEvent.change(screen.getByLabelText("labelStudio.height"), {
      target: { value: "30" },
    });
    fireEvent.click(screen.getByRole("button", { name: "labelStudio.apply" }));
    expect(screen.getByText("labelStudio.attribution")).toBeInTheDocument();
    await waitFor(() =>
      expect(mocks.preview).toHaveBeenLastCalledWith(
        12,
        expect.objectContaining({
          label: expect.objectContaining({ attribution: "full" }),
        }),
        expect.any(AbortSignal),
      ),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "labelStudio.download" }),
      ).not.toBeDisabled(),
    );
  });

  it("remembers orientation for the tab session and applies it to each preset", async () => {
    const first = open();
    fireEvent.click(
      await screen.findByRole("button", { name: "labelStudio.portrait" }),
    );
    expect(screen.getByLabelText("labelStudio.width")).toHaveValue("30");
    expect(screen.getByLabelText("labelStudio.height")).toHaveValue("50");
    fireEvent.click(screen.getByRole("button", { name: "12 × 40" }));
    expect(screen.getByLabelText("labelStudio.width")).toHaveValue("12");
    first.unmount();
    open();
    expect(
      await screen.findByRole("button", { name: "labelStudio.portrait" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("labelStudio.width")).toHaveValue("30");
    fireEvent.click(
      screen.getByRole("button", { name: "labelStudio.classic" }),
    );
    expect(
      screen.queryByRole("group", { name: "labelStudio.orientation" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "labelStudio.full" }));
    expect(
      screen.getByRole("button", { name: "labelStudio.portrait" }),
    ).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(
      screen.getByRole("button", { name: "labelStudio.landscape" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "40 × 12" }));
    expect(screen.getByLabelText("labelStudio.width")).toHaveValue("40");
    expect(screen.getByLabelText("labelStudio.height")).toHaveValue("12");
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "labelStudio.download" }),
      ).not.toBeDisabled(),
    );
  });
});
