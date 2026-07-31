export function formatDecimalInput(value: number, fractionDigits = 1): string {
  if (!Number.isFinite(value)) return '';

  const factor = 10 ** fractionDigits;
  return String(Math.round((value + Number.EPSILON) * factor) / factor);
}

export function parseDecimalInput(value: string): number {
  const normalized = value.trim().replace(',', '.');
  if (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(normalized)) {
    return Number.NaN;
  }
  return Number(normalized);
}
