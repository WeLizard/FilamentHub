const GCODE_FILE_SUFFIXES = ['.gcode.3mf', '.gcode.gz', '.gcode', '.txt'];

export const quoteTitleFromFileName = (fileName: string, fallback: string): string => {
  const leafName = fileName.split(/[\\/]/).pop()?.trim() ?? '';
  const lowerName = leafName.toLocaleLowerCase();
  const matchedSuffix = GCODE_FILE_SUFFIXES.find((suffix) => lowerName.endsWith(suffix));
  const withoutSuffix = matchedSuffix
    ? leafName.slice(0, Math.max(0, leafName.length - matchedSuffix.length))
    : leafName;
  return withoutSuffix.trim() || fallback;
};

export const allocateRoundedTotal = (total: number, rawWeights: number[]): number[] => {
  if (rawWeights.length === 0) return [];

  const safeTotal = Number.isFinite(total) ? Math.max(0, total) : 0;
  const weights = rawWeights.map((weight) => (
    Number.isFinite(weight) && weight > 0 ? weight : 0
  ));
  const weightTotal = weights.reduce((sum, weight) => sum + weight, 0);
  const normalizedWeights = weightTotal > 0
    ? weights
    : weights.map(() => 1);
  const normalizedTotal = normalizedWeights.reduce((sum, weight) => sum + weight, 0);

  let allocated = 0;
  return normalizedWeights.map((weight, index) => {
    if (index === normalizedWeights.length - 1) {
      return Number((safeTotal - allocated).toFixed(2));
    }
    const value = Number(((safeTotal * weight) / normalizedTotal).toFixed(2));
    allocated += value;
    return value;
  });
};

/** Make the quantity × cent-priced unit values reproduce the saved line amount. */
export const normalizeQuoteLineUnitPrice = <T extends {
  quantity: number;
  unitPrice: number;
  totalPrice: number;
}>(line: T): T[] | null => {
  if (!Number.isFinite(line.quantity) || line.quantity <= 0 || !Number.isFinite(line.totalPrice) || line.totalPrice < 0) return null;
  const totalCents = Math.round(line.totalPrice * 100 + Number.EPSILON);
  if (Number.isInteger(line.quantity)) {
    const lowUnitCents = Math.floor(totalCents / line.quantity);
    const highCount = totalCents - lowUnitCents * line.quantity;
    const lowCount = line.quantity - highCount;
    const normalized: T[] = [];
    if (lowCount > 0) normalized.push({
      ...line,
      quantity: lowCount,
      unitPrice: lowUnitCents / 100,
      totalPrice: lowCount * lowUnitCents / 100,
    });
    if (highCount > 0) normalized.push({
      ...line,
      quantity: highCount,
      unitPrice: (lowUnitCents + 1) / 100,
      totalPrice: highCount * (lowUnitCents + 1) / 100,
    });
    return normalized;
  }

  const unitCents = Math.round(line.unitPrice * 100 + Number.EPSILON);
  const apiLineCents = Math.round(line.quantity * unitCents);
  return apiLineCents === totalCents
    ? [{ ...line, unitPrice: unitCents / 100, totalPrice: totalCents / 100 }]
    : null;
};
