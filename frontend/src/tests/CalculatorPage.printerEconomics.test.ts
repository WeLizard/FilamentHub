import { describe, expect, it } from 'vitest';

import {
  buildEstimateRequest,
  isJobMachineRateMissing,
  isMachineRateMissing,
  resolveGcodeParseError,
} from '../pages/CalculatorPage';
import type { PrinterEconomics } from '../api/client';
import type { TFunction } from 'i18next';

const form = {
  selectedFilamentId: '' as const,
  weightG: 100,
  spoolPrice: 1200,
  spoolWeightKg: 1,
  quantity: 1,
  timeHours: 2,
  timeMinutes: 0,
  timeSec: 0,
  printerPowerW: 350,
  printingRatePerHour: 170,
  amortizationRatePerHour: 16,
  electricityCostPerKwh: 6,
} as unknown as Parameters<typeof buildEstimateRequest>[0];

const economics = (overrides: Partial<PrinterEconomics> = {}): PrinterEconomics => ({
  printer_id: 1,
  configured: true,
  purchase_cost: 90000,
  residual_value: null,
  useful_life_hours: 7000,
  average_power_watts: 400,
  power_hotend_w: null,
  power_bed_w: null,
  power_steppers_w: null,
  power_electronics_w: null,
  maintenance_cost_per_hour: 5,
  machine_hour_rate: 40,
  economics_currency: 'RUB',
  calculator_currency: 'RUB',
  depreciation_per_hour: 12.86,
  electricity_per_hour: 2.4,
  maintenance_per_hour: 5,
  machine_cost_per_hour: 20.26,
  effective_machine_hour_rate: 40,
  rate_below_cost: false,
  calculator_printer_power_w: 400,
  calculator_printing_rate_per_hour: 19.74,
  calculator_amortization_rate_per_hour: 17.86,
  calculator_electricity_cost_per_kwh: 6,
  sources: { rate: 'printer' },
  ...overrides,
});

describe('buildEstimateRequest with a chosen machine', () => {
  it('still charges wear when no machine is chosen', () => {
    // Wear stopped being a field of its own; it must not stop reaching the price.
    const request = buildEstimateRequest(form, [], [], [], null);

    expect(request.amortization_rate_per_hour).toBe(16);
  });

  it('charges the account rate as the whole hour, wear and power included', () => {
    const request = buildEstimateRequest(form, [], [], [], null);

    expect(request.printer_power_w).toBe(350);
    // 170 for the hour, of which 16 of wear and 2.1 of power are billed as their own lines.
    expect(request.printing_rate_per_hour).toBe(151.9);
    expect(request.amortization_rate_per_hour).toBe(16);
  });

  it('uses the resolved account fallback for a machine nobody has set up', () => {
    const accountFallback = economics({
      configured: false,
      effective_machine_hour_rate: 170,
      calculator_printer_power_w: 350,
      calculator_printing_rate_per_hour: 151.9,
      calculator_amortization_rate_per_hour: 16,
      sources: { rate: 'account' },
    });
    const request = buildEstimateRequest(form, [], [], [], accountFallback);

    expect(request.printing_rate_per_hour).toBe(151.9);
    expect(request.amortization_rate_per_hour).toBe(16);
  });

  it('uses the Orca fallback even when the machine has no economics fields of its own', () => {
    const orcaFallback = economics({
      configured: false,
      effective_machine_hour_rate: 80,
      calculator_printing_rate_per_hour: 61.9,
      sources: { rate: 'orca' },
    });
    const request = buildEstimateRequest(form, [], [], [], orcaFallback);

    expect(request.printing_rate_per_hour).toBe(61.9);
    expect(request.amortization_rate_per_hour).toBe(17.86);
  });

  it('charges the machine for this order only', () => {
    const request = buildEstimateRequest(form, [], [], [], economics(), 'RUB');

    expect(request.printer_power_w).toBe(400);
    expect(request.printing_rate_per_hour).toBe(19.74);
    expect(request.amortization_rate_per_hour).toBe(17.86);
    // The person's own defaults are untouched — this is what keeps a pick from
    // rewriting the account-wide economics.
    expect(form.printingRatePerHour).toBe(170);
    expect(form.amortizationRatePerHour).toBe(16);
  });

  it('does not relabel machine economics from another currency', () => {
    const request = buildEstimateRequest(
      form,
      [],
      [],
      [],
      economics({ economics_currency: 'USD', calculator_currency: 'RUB' }),
      'EUR',
    );

    expect(request.printer_power_w).toBe(350);
    expect(request.printing_rate_per_hour).toBe(151.9);
    expect(request.amortization_rate_per_hour).toBe(16);
  });

  it('uses account-currency values resolved from a printer stored in another currency', () => {
    const request = buildEstimateRequest(
      form,
      [],
      [],
      [],
      economics({
        economics_currency: 'USD',
        calculator_currency: 'RUB',
        effective_machine_hour_rate: 170,
        calculator_printing_rate_per_hour: 151.9,
        calculator_amortization_rate_per_hour: 16,
        sources: { rate: 'account', printer_money: 'currency_mismatch' },
      }),
      'RUB',
    );

    expect(request.printer_power_w).toBe(400);
    expect(request.printing_rate_per_hour).toBe(151.9);
    expect(request.amortization_rate_per_hour).toBe(16);
  });

  it('never lets a rate under its own cost make an order cheaper', () => {
    const request = buildEstimateRequest(
      form,
      [],
      [],
      [],
      economics({ calculator_printing_rate_per_hour: 0, rate_below_cost: true }),
    );

    expect(request.printing_rate_per_hour).toBe(0);
    expect(request.amortization_rate_per_hour).toBeGreaterThan(0);
    expect(
      (request.amortization_rate_per_hour ?? 0)
      + ((request.printer_power_w ?? 0) / 1000) * (request.electricity_cost_per_kwh ?? 0),
    ).toBeCloseTo(20.26);
  });
});

describe('machine-hour rate warning', () => {
  it('warns when neither the printer nor any fallback supplied a rate', () => {
    expect(isMachineRateMissing(economics({
      configured: false,
      effective_machine_hour_rate: 0,
      calculator_printing_rate_per_hour: 0,
      sources: { rate: 'none' },
    }), 170)).toBe(true);
  });

  it.each(['account', 'orca'] as const)(
    'accepts a real %s fallback for an unconfigured printer',
    (rateSource) => {
      expect(isMachineRateMissing(economics({
        configured: false,
        effective_machine_hour_rate: 80,
        sources: { rate: rateSource },
      }), 0)).toBe(false);
    },
  );

  it('does not call a deliberately below-cost rate missing', () => {
    expect(isMachineRateMissing(economics({
      effective_machine_hour_rate: 10,
      calculator_printing_rate_per_hour: 0,
      rate_below_cost: true,
      sources: { rate: 'printer' },
    }), 0)).toBe(false);
  });

  it('uses the account field when no physical printer is selected', () => {
    expect(isMachineRateMissing(null, 0)).toBe(true);
    expect(isMachineRateMissing(null, 170)).toBe(false);
  });

  it('detects the one unpriced printer in a mixed batch', () => {
    const configured = economics({ printer_id: 1, sources: { rate: 'printer' } });
    const missing = economics({
      printer_id: 2,
      effective_machine_hour_rate: 0,
      calculator_printing_rate_per_hour: 0,
      sources: { rate: 'none' },
    });
    const byPrinter = new Map([[1, configured], [2, missing]]);
    const job = (printerId: number) => ({
      jobKey: `job-${printerId}`,
      repeats: 1,
      quoteMode: 'set' as const,
      printTimeSeconds: 3600,
      physicalPrinterId: printerId,
    });

    expect(isJobMachineRateMissing(job(1), configured, 0, byPrinter)).toBe(false);
    expect(isJobMachineRateMissing(job(2), configured, 0, byPrinter)).toBe(true);
  });
});

describe('batch G-code parse errors', () => {
  it('shows localized user text when every file fails', () => {
    const localizedMessage = 'None of the selected G-code files could be parsed.';
    const t = ((key: string) => (
      key === 'profilePage.calculator.batchParseAllFailed' ? localizedMessage : key
    )) as TFunction;

    const message = resolveGcodeParseError(new Error('all_gcode_files_failed'), t);

    expect(message).toBe(localizedMessage);
    expect(message).not.toContain('all_gcode_files_failed');
  });
});
