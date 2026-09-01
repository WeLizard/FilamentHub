import { afterEach, describe, expect, it, vi } from "vitest";
import { printPdfBlob } from "./download";

describe("printPdfBlob", () => {
  afterEach(() => vi.restoreAllMocks());

  it("loads the exact PDF in an isolated frame before opening print", async () => {
    const createObjectURL = vi
      .spyOn(URL, "createObjectURL")
      .mockReturnValue("blob:print-pdf");
    const revokeObjectURL = vi
      .spyOn(URL, "revokeObjectURL")
      .mockImplementation(() => undefined);
    const append = vi.spyOn(document.body, "appendChild");
    vi.spyOn(window, "setTimeout").mockReturnValue(1);
    const promise = printPdfBlob(
      new Blob(["pdf"], { type: "application/pdf" }),
    );
    const frame = append.mock.calls[0][0] as HTMLIFrameElement;
    const focus = vi.fn();
    const print = vi.fn();
    let afterPrint: (() => void) | undefined;
    Object.defineProperty(frame, "contentWindow", {
      configurable: true,
      value: {
        focus,
        print,
        addEventListener: vi.fn((type: string, callback: () => void) => {
          if (type === "afterprint") afterPrint = callback;
        }),
      },
    });
    frame.dispatchEvent(new Event("load"));

    await expect(promise).resolves.toBeUndefined();
    expect(frame.src).toBe("blob:print-pdf");
    expect(focus).toHaveBeenCalledOnce();
    expect(print).toHaveBeenCalledOnce();
    expect(createObjectURL).toHaveBeenCalledOnce();

    afterPrint?.();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:print-pdf");
  });
});
