import { describe, expect, it } from 'vitest';

import {
  buildCalculatorBatchSummary,
  buildConfiguredCalculatorBatchSummary,
  calculatorOutputQuantityPerRun,
  canSplitCalculatorObjectGroups,
} from './calculatorBatch';

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

  it('keeps independent repeats and commercial output for each plate', () => {
    const summary = buildConfiguredCalculatorBatchSummary([
      {
        repeats: 2,
        outputQuantityPerRun: 200,
        objectCount: 200,
        printTimeSeconds: 3600,
        weightG: 100,
      },
      {
        repeats: 3,
        outputQuantityPerRun: 1,
        objectCount: 4,
        printTimeSeconds: 1800,
        weightG: 50,
      },
    ]);

    expect(summary).toEqual({
      jobCount: 2,
      printRunCount: 5,
      physicalObjectCount: 412,
      quoteQuantity: 403,
      partyPrintTimeSeconds: 12_600,
      partyWeightG: 350,
    });
  });

  it('allows group splitting only with evidence for every group', () => {
    const complete = [
      { count: 2, extrusion_share: 0.4 },
      { count: 1, extrusion_share: 0.6 },
    ];

    expect(canSplitCalculatorObjectGroups(complete)).toBe(true);
    expect(calculatorOutputQuantityPerRun(complete, 'groups')).toBe(3);
    expect(calculatorOutputQuantityPerRun(complete, 'set')).toBe(1);
    expect(canSplitCalculatorObjectGroups([
      { count: 2, extrusion_share: null },
      { count: 1, extrusion_share: 0.6 },
    ])).toBe(false);
  });
});
