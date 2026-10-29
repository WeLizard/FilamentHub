/** "2026-07" → "июль 2026" / "Jul 2026" / "2026年7月" in the interface language. */
export function formatMonthLabel(month: string, language: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  if (!match) return month;
  const date = new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, 1));
  return new Intl.DateTimeFormat(language, { month: 'long', year: 'numeric', timeZone: 'UTC' }).format(date);
}
