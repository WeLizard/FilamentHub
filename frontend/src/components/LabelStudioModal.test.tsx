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
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key} ${JSON.stringify(options)}` : key,
    i18n: { language: "ru" },
  }),
}));
vi.mock("./Toast", () => ({ toast: { error: mocks.error } }));

describe("LabelStudioModal", () => {
  beforeEach(() => {
    vi.resetAllMocks();
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
      sheet_media: {
        a4: { width_mm: 210, height_mm: 297 },
        letter: { width_mm: 215.9, height_mm: 279.4 },
      },
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
    const content = screen.getByRole("group", { name: "labelStudio.content" });
    expect(content).toContainElement(screen.getByLabelText("labelStudio.file"));
    expect(content).toContainElement(
      screen.getByLabelText("labelStudio.media"),
    );
    expect(content).toContainElement(download);
    expect(
      screen.queryByRole("group", { name: "labelStudio.export" }),
    ).not.toBeInTheDocument();
    expect(screen.getByLabelText("labelStudio.brandLogo")).toBeDisabled();
    expect(screen.getByLabelText("labelStudio.brandLogo")).not.toBeChecked();
    fireEvent.click(
      screen.getByRole("button", { name: "labelStudio.classic" }),
    );
    expect(download).toBeDisabled();
    expect(screen.getByLabelText("labelStudio.centerMark")).toBeChecked();
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
        1,
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
    fireEvent.focus(
      screen.getByLabelText('labelStudio.fieldPosition {"position":1}'),
    );
    fireEvent.click(
      await screen.findByRole("button", { name: "labelStudio.fieldEmpty" }),
    );
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
        1,
      ),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "labelStudio.orientation" }),
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
        1,
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
        1,
      ),
    );
    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: "labelStudio.download" }),
      ).not.toBeDisabled(),
    );
  });

  it("supports six configurable positions, swaps occupied fields and removes fields without inventing values", async () => {
    const metadata = await mocks.metadata();
    metadata.data.fields.push(
      ["bed", "Bed", "75–90 °C"],
      ["drying", "Drying", "65 °C · 6 h"],
      ["abrasiveness", "Hardness", "≥55 HRC"],
      ["diameter", "Diameter", "1.75 mm"],
      ["density", "Density", "1.25 g/cm³"],
      ["weight", "Weight", "1000 g"],
    );
    open();
    const slot = (position: number) =>
      screen.getByLabelText(
        `labelStudio.fieldPosition {"position":${position}}`,
      );
    await screen.findByLabelText('labelStudio.fieldPosition {"position":1}');
    expect(
      screen.getAllByRole("textbox", { name: /labelStudio.fieldPosition/ }),
    ).toHaveLength(6);
    expect(
      screen.queryByRole("checkbox", { name: /Nozzle|Bed/ }),
    ).not.toBeInTheDocument();
    fireEvent.focus(slot(1));
    fireEvent.click(await screen.findByRole("button", { name: "Bed" }));
    expect(slot(1)).toHaveValue("Bed");
    expect(slot(2)).toHaveValue("Nozzle");
    fireEvent.focus(slot(6));
    fireEvent.click(await screen.findByRole("button", { name: "Weight" }));
    fireEvent.focus(slot(3));
    fireEvent.click(
      await screen.findByRole("button", { name: "labelStudio.fieldEmpty" }),
    );
    await waitFor(() =>
      expect(mocks.preview.mock.lastCall?.[1].label.fields).toEqual([
        "bed",
        "nozzle",
        "abrasiveness",
        "diameter",
        "weight",
      ]),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "labelStudio.classic" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "labelStudio.full" }));
    expect(slot(6)).toHaveValue("Weight");
    expect(slot(3)).toHaveValue("labelStudio.fieldEmpty");
  });

  it("prefills an A4 grid and exports the full multi-page quantity from a partial first sheet", async () => {
    open();
    fireEvent.focus(await screen.findByLabelText("labelStudio.media"));
    fireEvent.click(
      await screen.findByRole("button", { name: "labelStudio.a4" }),
    );
    expect(screen.getByLabelText("labelStudio.copies")).toHaveValue(27);
    expect(
      screen.getByText(
        'labelStudio.sheetGrid {"columns":3,"rows":9,"capacity":27}',
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "labelStudio.showLabel" }),
    ).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("labelStudio.copies"), {
      target: { value: "50" },
    });
    fireEvent.change(screen.getByLabelText("labelStudio.start"), {
      target: { value: "27" },
    });
    expect(
      screen.getByText('labelStudio.sheetCount {"copies":50,"pages":3}'),
    ).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "labelStudio.nextPage" }),
    );
    await waitFor(() =>
      expect(mocks.preview).toHaveBeenLastCalledWith(
        12,
        expect.objectContaining({
          media: "a4",
          copies: 50,
          start_position: 27,
        }),
        expect.any(AbortSignal),
        2,
      ),
    );
    const download = screen.getByRole("button", {
      name: "labelStudio.download",
    });
    await waitFor(() => expect(download).not.toBeDisabled());
    fireEvent.click(download);
    await waitFor(() =>
      expect(mocks.download).toHaveBeenCalledWith(
        12,
        expect.objectContaining({
          format: "pdf",
          media: "a4",
          copies: 50,
          start_position: 27,
        }),
      ),
    );
    fireEvent.focus(screen.getByLabelText("labelStudio.file"));
    fireEvent.click(await screen.findByRole("button", { name: "SVG" }));
    expect(download).toBeDisabled();
    expect(screen.getByText("labelStudio.multiplePdf")).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", { name: "labelStudio.fillSheet" }),
    );
    expect(screen.getByLabelText("labelStudio.copies")).toHaveValue(1);
    expect(
      screen.getByText('labelStudio.pageNumber {"page":1,"total":1}'),
    ).toBeInTheDocument();
    await waitFor(() => expect(download).not.toBeDisabled());
  });

  it("keeps the automatic quantity bounded and blocks media that cannot fit the label", async () => {
    open();
    fireEvent.focus(await screen.findByLabelText("labelStudio.media"));
    fireEvent.click(
      await screen.findByRole("button", { name: "labelStudio.letter" }),
    );
    expect(screen.getByLabelText("labelStudio.copies")).toHaveValue(24);
    fireEvent.click(screen.getByRole("button", { name: "40 × 12" }));
    expect(screen.getByLabelText("labelStudio.copies")).toHaveValue(50);
    fireEvent.change(screen.getByLabelText("labelStudio.width"), {
      target: { value: "220" },
    });
    fireEvent.change(screen.getByLabelText("labelStudio.height"), {
      target: { value: "220" },
    });
    fireEvent.click(screen.getByRole("button", { name: "labelStudio.apply" }));
    expect(
      screen.getByRole("button", { name: "labelStudio.download" }),
    ).toBeDisabled();
    expect(
      screen.getByRole("button", { name: "labelStudio.fillSheet" }),
    ).toBeDisabled();
    expect(
      screen.getAllByText("labelStudio.sheetDoesNotFit").length,
    ).toBeGreaterThan(0);
  });

  it("remembers orientation for the tab session and applies it to each preset", async () => {
    const first = open();
    fireEvent.click(
      await screen.findByRole("button", { name: "labelStudio.orientation" }),
    );
    expect(screen.getByLabelText("labelStudio.width")).toHaveValue("30");
    expect(screen.getByLabelText("labelStudio.height")).toHaveValue("50");
    fireEvent.click(screen.getByRole("button", { name: "12 × 40" }));
    expect(screen.getByLabelText("labelStudio.width")).toHaveValue("12");
    first.unmount();
    open();
    expect(
      await screen.findByRole("button", { name: "labelStudio.orientation" }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByLabelText("labelStudio.width")).toHaveValue("30");
    fireEvent.click(
      screen.getByRole("button", { name: "labelStudio.classic" }),
    );
    expect(
      screen.queryByRole("button", { name: "labelStudio.orientation" }),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "labelStudio.full" }));
    expect(
      screen.getByRole("button", { name: "labelStudio.orientation" }),
    ).toHaveAttribute("aria-pressed", "true");
    fireEvent.click(
      screen.getByRole("button", { name: "labelStudio.orientation" }),
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

  it("exports the chosen edge frame and sheet-only cut guides without shifting the grid", async () => {
    open();
    fireEvent.click(await screen.findByLabelText("labelStudio.border"));
    fireEvent.focus(screen.getByLabelText("labelStudio.media"));
    fireEvent.click(
      await screen.findByRole("button", { name: "labelStudio.a4" }),
    );
    expect(screen.getByText("labelStudio.startHint")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("labelStudio.margin"), {
      target: { value: "2" },
    });
    expect(screen.getByLabelText("labelStudio.cropMarks")).toBeDisabled();
    fireEvent.change(screen.getByLabelText("labelStudio.margin"), {
      target: { value: "3" },
    });
    const quantity = screen.getByLabelText("labelStudio.copies");
    const originalQuantity = quantity.getAttribute("value");
    fireEvent.click(screen.getByLabelText("labelStudio.cropMarks"));
    expect(quantity).toHaveAttribute("value", originalQuantity);
    expect(screen.getByLabelText("labelStudio.margin")).toHaveAttribute(
      "min",
      "3",
    );
    await waitFor(() =>
      expect(mocks.preview.mock.lastCall?.[1]).toEqual(
        expect.objectContaining({
          label: expect.objectContaining({ border: true }),
          media: "a4",
          crop_marks: true,
          page_margin_mm: 3,
        }),
      ),
    );
    const download = screen.getByRole("button", {
      name: "labelStudio.download",
    });
    await waitFor(() => expect(download).not.toBeDisabled());
    fireEvent.click(download);
    await waitFor(() =>
      expect(mocks.download).toHaveBeenCalledWith(
        12,
        expect.objectContaining({
          label: expect.objectContaining({ border: true }),
          crop_marks: true,
        }),
      ),
    );
    fireEvent.focus(screen.getByLabelText("labelStudio.media"));
    fireEvent.click(
      await screen.findByRole("button", { name: "labelStudio.single" }),
    );
    expect(
      screen.queryByLabelText("labelStudio.cropMarks"),
    ).not.toBeInTheDocument();
    await waitFor(() =>
      expect(mocks.preview.mock.lastCall?.[1]).toEqual(
        expect.objectContaining({
          label: expect.objectContaining({ border: true }),
          media: "single",
          crop_marks: false,
        }),
      ),
    );
  });
});
