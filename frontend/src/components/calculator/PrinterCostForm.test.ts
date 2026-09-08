import { describe, expect, it } from 'vitest';

import type { PrinterEconomics } from '../../api/client';
import { calculateDepreciationPerHour, resolveEditableMachineRate } from './PrinterCostForm';

const economics = (overrides: Partial<PrinterEconomics>): PrinterEconomics => ({
  machine_hour_rate: null,
  effective_machine_hour_rate: 0,
  sources: { rate: 'none' },
  ...overrides,
} as PrinterEconomics);

describe('resolveEditableMachineRate', () => {
  it('shows an Orca fallback instead of an unrelated zero account default', () => {
    expect(resolveEditableMachineRate(economics({
      effective_machine_hour_rate: 80,
      sources: { rate: 'orca' },
    }), 0)).toBe(80);
  });

  it('keeps printer input first and account fallback second', () => {
    expect(resolveEditableMachineRate(economics({
      machine_hour_rate: 45,
      effective_machine_hour_rate: 45,
      sources: { rate: 'printer' },
    }), 170)).toBe(45);
    expect(resolveEditableMachineRate(economics({
      effective_machine_hour_rate: 170,
      sources: { rate: 'account' },
    }), 170)).toBe(170);
  });

  it('does not relabel an account fallback as printer money in another currency', () => {
    expect(resolveEditableMachineRate(economics({
      economics_currency: 'USD',
      calculator_currency: 'RUB',
      effective_machine_hour_rate: 170,
      sources: { rate: 'account' },
    }), 170)).toBe(0);
  });
});

describe('calculateDepreciationPerHour', () => {
  it('keeps a saved residual value in the form preview', () => {
    expect(calculateDepreciationPerHour(120_000, 7000, 15_000)).toBe(15);
  });

  it('never turns residual value into negative wear', () => {
    expect(calculateDepreciationPerHour(10_000, 1000, 12_000)).toBe(0);
  });
});
