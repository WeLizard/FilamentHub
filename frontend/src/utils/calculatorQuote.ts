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
