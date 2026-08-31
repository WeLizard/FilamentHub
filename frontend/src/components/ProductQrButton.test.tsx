import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ProductQrButton } from "./ProductQrButton";

const mocks = vi.hoisted(() => ({
  download: vi.fn(),
  copy: vi.fn(),
  success: vi.fn(),
}));
vi.mock("../api/client", () => ({
  qrAPI: {
    getQRCodeURL: (id: number) => `/qr-image/${id}`,
    downloadQRCode: mocks.download,
  },
}));
vi.mock("./Toast", () => ({ toast: { success: mocks.success } }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { format?: string }) =>
      options?.format ? `${key} ${options.format}` : key,
    i18n: { language: "ru" },
  }),
}));

const filament = {
  id: 41,
  name: "Deep Ocean",
  qr_code: "FH-OCEAN",
  slug: "deep-ocean",
  brand_slug: "olgacraft",
};

describe("public product QR", () => {
  beforeEach(() => {
    mocks.download.mockReset().mockResolvedValue(undefined);
    mocks.copy.mockReset().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: mocks.copy },
    });
  });

  it("offers only product viewing, classic downloads and a public link, without opening the label editor", async () => {
    render(<ProductQrButton filament={filament} />);
    fireEvent.click(screen.getByRole("button", { name: "productQr.title" }));
    expect(
      screen.getByRole("dialog", { name: "productQr.title" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("img")).toHaveAttribute("src", "/qr-image/41");
    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    expect(screen.queryByText("labelStudio.title")).not.toBeInTheDocument();
    for (const format of ["png", "svg"]) {
      const button = screen.getByRole("button", {
        name: `productQr.download ${format.toUpperCase()}`,
      });
      await waitFor(() => expect(button).not.toBeDisabled());
      fireEvent.click(button);
      await waitFor(() =>
        expect(mocks.download).toHaveBeenLastCalledWith(41, 600, { format }),
      );
    }
    fireEvent.click(screen.getByRole("button", { name: "productQr.copyLink" }));
    await waitFor(() =>
      expect(mocks.copy).toHaveBeenCalledWith(
        "https://filamenthub.ru/ru/brands/olgacraft/filaments/deep-ocean",
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "common.close" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("does not offer an absent QR and keeps file download available after preview failure", async () => {
    const { rerender } = render(
      <ProductQrButton filament={{ ...filament, qr_code: null }} />,
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    rerender(<ProductQrButton filament={filament} />);
    fireEvent.click(screen.getByRole("button", { name: "productQr.title" }));
    fireEvent.error(screen.getByRole("img"));
    expect(screen.getByRole("alert")).toHaveTextContent(
      "productQr.imageFailed",
    );
    fireEvent.click(
      screen.getByRole("button", { name: "productQr.download SVG" }),
    );
    await waitFor(() =>
      expect(mocks.download).toHaveBeenCalledWith(41, 600, { format: "svg" }),
    );
  });
});
