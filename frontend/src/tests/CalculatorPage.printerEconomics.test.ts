import { describe, expect, it } from 'vitest';

import { buildEstimateRequest } from '../pages/CalculatorPage';
import type { PrinterEconomics } from '../api/client';

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

  it('leaves the account defaults alone when no printer is chosen', () => {
    const request = buildEstimateRequest(form, [], [], [], null);

    expect(request.printer_power_w).toBe(350);
    expect(request.printing_rate_per_hour).toBe(170);
    expect(request.amortization_rate_per_hour).toBe(16);
  });

  it('leaves them alone for a machine nobody has set up', () => {
    const request = buildEstimateRequest(form, [], [], [], economics({ configured: false }));

    expect(request.printing_rate_per_hour).toBe(170);
    expect(request.amortization_rate_per_hour).toBe(16);
  });

  it('charges the machine for this order only', () => {
    const request = buildEstimateRequest(form, [], [], [], economics());

    expect(request.printer_power_w).toBe(400);
    expect(request.printing_rate_per_hour).toBe(19.74);
    expect(request.amortization_rate_per_hour).toBe(17.86);
    // The person's own defaults are untouched — this is what keeps a pick from
    // rewriting the account-wide economics.
    expect(form.printingRatePerHour).toBe(170);
    expect(form.amortizationRatePerHour).toBe(16);
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
  });
});
