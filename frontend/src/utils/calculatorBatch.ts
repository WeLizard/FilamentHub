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

export type CalculatorQuoteMode = 'set' | 'groups';

export interface CalculatorObjectGroupLike {
  count: number;
  extrusion_share?: number | null;
}

export interface CalculatorConfiguredJobSource extends CalculatorBatchSource {
  repeats: number;
  outputQuantityPerRun: number;
}

export interface CalculatorConfiguredBatchSummary {
  jobCount: number;
  printRunCount: number;
  physicalObjectCount: number;
  quoteQuantity: number;
  partyPrintTimeSeconds: number;
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

export const canSplitCalculatorObjectGroups = (
  groups: CalculatorObjectGroupLike[],
): boolean => groups.length > 1 && groups.every(
  (group) => group.count > 0 && (group.extrusion_share ?? 0) > 0,
);

export const calculatorOutputQuantityPerRun = (
  groups: CalculatorObjectGroupLike[],
  quoteMode: CalculatorQuoteMode,
): number => {
  if (quoteMode !== 'groups' || groups.length === 0) return 1;
  return Math.max(1, groups.reduce((sum, group) => sum + Math.max(0, Math.floor(group.count)), 0));
};

export const buildConfiguredCalculatorBatchSummary = (
  sources: CalculatorConfiguredJobSource[],
): CalculatorConfiguredBatchSummary => sources.reduce<CalculatorConfiguredBatchSummary>(
  (summary, source) => {
    const repeats = Math.max(1, Math.floor(nonNegativeNumber(source.repeats)));
    const physicalObjectsPerRun = Math.max(1, Math.floor(nonNegativeNumber(source.objectCount)));
    const outputQuantityPerRun = Math.max(1, Math.floor(nonNegativeNumber(source.outputQuantityPerRun)));
    return {
      jobCount: summary.jobCount + 1,
      printRunCount: summary.printRunCount + repeats,
      physicalObjectCount: summary.physicalObjectCount + physicalObjectsPerRun * repeats,
      quoteQuantity: summary.quoteQuantity + outputQuantityPerRun * repeats,
      partyPrintTimeSeconds:
        summary.partyPrintTimeSeconds + nonNegativeNumber(source.printTimeSeconds) * repeats,
      partyWeightG: summary.partyWeightG + nonNegativeNumber(source.weightG) * repeats,
    };
  },
  {
    jobCount: 0,
    printRunCount: 0,
    physicalObjectCount: 0,
    quoteQuantity: 0,
    partyPrintTimeSeconds: 0,
    partyWeightG: 0,
  },
);
