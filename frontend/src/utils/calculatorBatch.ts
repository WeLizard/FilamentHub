export interface CalculatorBatchSource {
  printTimeSeconds?: number | null;
  weightG?: number | null;
  objectCount?: number | null;
}

export interface CalculatorBatchSummary {
  jobCount: number;
  repeatCount: number;
  printRunCount: number;
  objectCountPerSet: number;
  outputObjectCount: number;
  printTimeSecondsPerSet: number;
  partyPrintTimeSeconds: number;
  weightGPerSet: number;
  partyWeightG: number;
}

const nonNegativeNumber = (value: number | null | undefined): number =>
  Number.isFinite(value) && (value ?? 0) > 0 ? Number(value) : 0;

export const buildCalculatorBatchSummary = (
  sources: CalculatorBatchSource[],
  repeats: number,
): CalculatorBatchSummary => {
  const repeatCount = Math.max(1, Math.floor(Number.isFinite(repeats) ? repeats : 1));
  const objectCountPerSet = sources.reduce(
    (sum, source) => sum + Math.max(1, Math.floor(nonNegativeNumber(source.objectCount))),
    0,
  );
  const printTimeSecondsPerSet = sources.reduce(
    (sum, source) => sum + nonNegativeNumber(source.printTimeSeconds),
    0,
  );
  const weightGPerSet = sources.reduce(
    (sum, source) => sum + nonNegativeNumber(source.weightG),
    0,
  );

  return {
    jobCount: sources.length,
    repeatCount,
    printRunCount: sources.length * repeatCount,
    objectCountPerSet,
    outputObjectCount: objectCountPerSet * repeatCount,
    printTimeSecondsPerSet,
    partyPrintTimeSeconds: printTimeSecondsPerSet * repeatCount,
    weightGPerSet,
    partyWeightG: weightGPerSet * repeatCount,
  };
};
