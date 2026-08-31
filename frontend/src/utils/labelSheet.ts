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
