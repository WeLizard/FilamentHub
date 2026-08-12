/** Format a byte count for compact file and attachment labels. */
export function formatBytes(value: number | null | undefined, locale: string): string {
  if (value === null || value === undefined || !Number.isFinite(value) || value < 0) return '';
  if (value < 1024) return `${value} B`;

  const formatter = new Intl.NumberFormat(locale, { maximumFractionDigits: 1 });
  if (value < 1024 * 1024) return `${formatter.format(value / 1024)} KB`;
  if (value < 1024 * 1024 * 1024) return `${formatter.format(value / (1024 * 1024))} MB`;
  return `${formatter.format(value / (1024 * 1024 * 1024))} GB`;
}
