import { describe, expect, it } from 'vitest';

import { buildCalculatorBatchSummary } from './calculatorBatch';

describe('buildCalculatorBatchSummary', () => {
  it('keeps a single G-code focused on one job and its actual object count', () => {
    expect(buildCalculatorBatchSummary([
      { printTimeSeconds: 3600, weightG: 42, objectCount: 1 },
    ], 1)).toEqual({
      jobCount: 1,
      repeatCount: 1,
      printRunCount: 1,
      objectCountPerSet: 1,
      outputObjectCount: 1,
      printTimeSecondsPerSet: 3600,
      partyPrintTimeSeconds: 3600,
      weightGPerSet: 42,
      partyWeightG: 42,
    });
  });

  it('multiplies the complete multi-file set without flattening objects into print runs', () => {
    const summary = buildCalculatorBatchSummary([
      { printTimeSeconds: 1200, weightG: 20, objectCount: 200 },
      { printTimeSeconds: 1800, weightG: 30, objectCount: 2 },
      { printTimeSeconds: 600, weightG: 10 },
      { printTimeSeconds: 2400, weightG: 40, objectCount: 4 },
      { printTimeSeconds: 3600, weightG: 50, objectCount: 1 },
    ], 2);

    expect(summary.jobCount).toBe(5);
    expect(summary.printRunCount).toBe(10);
    expect(summary.objectCountPerSet).toBe(208);
    expect(summary.outputObjectCount).toBe(416);
    expect(summary.partyPrintTimeSeconds).toBe(19_200);
    expect(summary.partyWeightG).toBe(300);
  });
});
