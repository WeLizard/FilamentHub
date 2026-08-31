/** Mirrors the renderer's physical grid; media dimensions come from its metadata. */
export function labelSheetGrid(
  media: { width_mm: number; height_mm: number } | undefined,
  label: { width_mm: number; height_mm: number },
  margin: number,
  gap: number,
) {
  if (!media) return { columns: 0, rows: 0, capacity: 0 };
  const columns = Math.max(
    0,
    Math.floor(
      (media.width_mm - 2 * margin + gap) / (label.width_mm + gap) + 1e-9,
    ),
  );
  const rows = Math.max(
    0,
    Math.floor(
      (media.height_mm - 2 * margin + gap) / (label.height_mm + gap) + 1e-9,
    ),
  );
  return { columns, rows, capacity: columns * rows };
}

/** Keep guides outside labels, with their axes at least 0.5 mm inside the page. */
export function labelCutGuideLimits(margin: number, gap: number) {
  const minGap = 0.5;
  const minMargin = gap / 2 + 0.5;
  return {
    minGap,
    minMargin,
    maxGap: Math.min(10, Math.max(0, 2 * (margin - 0.5))),
    allowed: gap >= minGap && margin >= minMargin,
  };
}
