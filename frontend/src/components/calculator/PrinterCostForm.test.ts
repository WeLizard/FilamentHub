import { describe, expect, it } from 'vitest';

import type { PrinterEconomics } from '../../api/client';
import {
  calculateDepreciationPerHour,
  printerEconomicsPatchForField,
  printerPowerPartPatch,
  resolveEditableMoneyValue,
  resolveEditableMachineRate,
} from './PrinterCostForm';

const economics = (overrides: Partial<PrinterEconomics>): PrinterEconomics => ({
  machine_hour_rate: null,
  effective_machine_hour_rate: 0,
  sources: { rate: 'none' },
  readiness: {
    version: 1,
    status: 'configured',
    money_currency: 'RUB',
    required_fields: [],
    reasons: [],
  },
  ...overrides,
} as PrinterEconomics);

describe('resolveEditableMachineRate', () => {
  it('shows an Orca fallback instead of an unrelated zero account default', () => {
    expect(resolveEditableMachineRate(economics({
      calculator_currency: 'RUB',
      effective_machine_hour_rate: 80,
      sources: { rate: 'orca' },
    }), 'RUB')).toBe(80);
  });

  it('keeps printer input first and account fallback second', () => {
    expect(resolveEditableMachineRate(economics({
      economics_currency: 'RUB',
      calculator_currency: 'RUB',
      machine_hour_rate: 45,
      effective_machine_hour_rate: 45,
      sources: { rate: 'printer' },
    }), 'RUB')).toBe(45);
    expect(resolveEditableMachineRate(economics({
      calculator_currency: 'RUB',
      effective_machine_hour_rate: 170,
      sources: { rate: 'account' },
    }), 'RUB')).toBe(170);
  });

  it('ignores a raw printer rate without currency and shows the compatible effective fallback', () => {
    expect(resolveEditableMachineRate(economics({
      economics_currency: null,
      calculator_currency: 'RUB',
      machine_hour_rate: 45,
      effective_machine_hour_rate: 170,
      sources: { rate: 'account' },
      readiness: {
        version: 1,
        status: 'configured',
        money_currency: 'RUB',
        required_fields: [{
          key: 'machine_hour_rate',
          value: 170,
          source: 'account_explicit',
          source_currency: 'RUB',
          usable: true,
          missing_reason: null,
        }],
        reasons: [],
      },
    }), 'RUB')).toBe(170);
  });

  it('ignores a raw printer rate in another currency', () => {
    expect(resolveEditableMachineRate(economics({
      economics_currency: 'USD',
      calculator_currency: 'RUB',
      machine_hour_rate: 45,
      effective_machine_hour_rate: 170,
      sources: { rate: 'account' },
      readiness: {
        version: 1,
        status: 'configured',
        money_currency: 'RUB',
        required_fields: [{
          key: 'machine_hour_rate',
          value: 170,
          source: 'account_explicit',
          source_currency: 'RUB',
          usable: true,
          missing_reason: null,
        }],
        reasons: [],
      },
    }), 'RUB')).toBe(170);
  });

  it('does not show an effective rate under an unrelated editor currency', () => {
    expect(resolveEditableMachineRate(economics({
      economics_currency: 'USD',
      calculator_currency: 'USD',
      machine_hour_rate: 45,
      effective_machine_hour_rate: 170,
      sources: { rate: 'printer' },
    }), 'RUB')).toBe(0);
  });
});

describe('resolveEditableMoneyValue', () => {
  it('requires an explicit matching currency before showing raw printer money', () => {
    expect(resolveEditableMoneyValue(120_000, null, 90_000, 'RUB', 'RUB', 'RUB')).toBe(90_000);
    expect(resolveEditableMoneyValue(120_000, 'USD', 90_000, 'RUB', 'RUB', 'RUB')).toBe(90_000);
  });

  it('returns zero when neither raw nor fallback money has the editor currency', () => {
    expect(resolveEditableMoneyValue(120_000, null, 90_000, null, 'RUB', 'RUB')).toBe(0);
    expect(resolveEditableMoneyValue(5, 'USD', 8, 'USD', 'USD', 'RUB')).toBe(0);
  });

  it('preserves matching raw purchase and maintenance values, including zero', () => {
    expect(resolveEditableMoneyValue(120_000, 'RUB', 90_000, 'RUB', 'RUB', 'RUB')).toBe(120_000);
    expect(resolveEditableMoneyValue(0, 'RUB', 8, 'RUB', 'RUB', 'RUB')).toBe(0);
  });

  it('ignores raw printer money when the backend applied another currency', () => {
    expect(resolveEditableMoneyValue(120_000, 'RUB', 90_000, 'USD', 'USD', 'RUB')).toBe(0);
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

describe('printer economics sparse patches', () => {
  it('sends only the field the person changed', () => {
    expect(printerEconomicsPatchForField('purchaseCost', 120_000)).toEqual({
      purchase_cost: 120_000,
    });
    expect(printerEconomicsPatchForField('powerWatts', 420)).toEqual({
      average_power_watts: 420,
    });
    expect(printerEconomicsPatchForField('powerWatts', 0)).toEqual({
      average_power_watts: null,
    });
  });

  it('keeps an explicit zero distinct from clearing a field', () => {
    expect(printerEconomicsPatchForField('maintenance', 0)).toEqual({
      maintenance_cost_per_hour: 0,
    });
    expect(printerEconomicsPatchForField('rate', 0)).toEqual({ machine_hour_rate: 0 });
    expect(printerEconomicsPatchForField('rate', null)).toEqual({ machine_hour_rate: null });
  });

  it('stores the editor currency together with fresh or mismatched money', () => {
    expect(printerEconomicsPatchForField('purchaseCost', 120_000, {
      stored: null,
      editor: 'RUB',
    })).toEqual({ purchase_cost: 120_000, economics_currency: 'RUB' });
    expect(printerEconomicsPatchForField('maintenance', 0, {
      stored: 'USD',
      editor: 'RUB',
    })).toEqual({ maintenance_cost_per_hour: 0, economics_currency: 'RUB' });
    expect(printerEconomicsPatchForField('rate', 80, {
      stored: 'RUB',
      editor: 'RUB',
    })).toEqual({ machine_hour_rate: 80 });
  });

  it('normalizes service life to the backend contract', () => {
    expect(printerEconomicsPatchForField('lifeHours', 7000.8)).toEqual({
      useful_life_hours: 7001,
    });
    expect(printerEconomicsPatchForField('lifeHours', 0)).toEqual({ useful_life_hours: null });
  });

  it('saves one edited power component without inventing an explicit total', () => {
    expect(printerPowerPartPatch('hotend', 40)).toEqual({ power_hotend_w: 40 });
    expect(printerPowerPartPatch('bed', null)).toEqual({ power_bed_w: null });
  });
});
