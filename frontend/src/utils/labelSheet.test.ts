import { describe, expect, it } from "vitest";
import { labelSheetGrid } from "./labelSheet";

describe("physical label sheet grid", () => {
  it.each([
    [210, 297, 50, 30, 5, 2, 3, 9],
    [215.9, 279.4, 50, 30, 5, 2, 3, 8],
    [210, 297, 30, 50, 5, 2, 6, 5],
    [210, 297, 40, 12, 5, 2, 4, 20],
    [215.9, 279.4, 63.5, 38.1, 5, 2, 3, 6],
    [210, 297, 220, 220, 5, 2, 0, 1],
    [210, 297, 8, 8, 0, 0, 26, 37],
  ])("%s×%s sheet, %s×%s label", (w, h, lw, lh, margin, gap, columns, rows) => {
    expect(
      labelSheetGrid(
        { width_mm: w, height_mm: h },
        { width_mm: lw, height_mm: lh },
        margin,
        gap,
      ),
    ).toEqual({ columns, rows, capacity: columns * rows });
  });
});
