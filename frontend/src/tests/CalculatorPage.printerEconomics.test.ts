import { describe, expect, it, vi } from 'vitest';

import {
  buildEstimateRequest,
  calculatorCurrencyAfterFailedSave,
  calculatorCurrencyFromProfile,
  calculatorProfilePatchForField,
  isLatestCalculatorProfileRequest,
  isJobMachineRateMissing,
  isMachineRateMissing,
  mergeCalculatorProfilePatches,
  reconcileCalculatorProfileForm,
  resolveGcodeParseError,
} from '../pages/CalculatorPage';
import type { PrinterEconomics } from '../api/client';
import type { CalculatorProfileResponse } from '../types/api';
import type { TFunction } from 'i18next';
import {
  economicsReadinessResultNoteKey,
  enqueueEconomicsSave,
} from '../utils/economicsReadiness';

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
  applied_sources: {
    currency: 'printer_explicit',
    machine_hour_rate: 'printer_explicit',
    electricity_cost_per_kwh: 'account_explicit',
    printer_power_w: 'printer_explicit',
    machine_wear_per_hour: 'printer_explicit',
  },
  readiness: {
    version: 1,
    status: 'configured',
    money_currency: 'RUB',
    required_fields: [{
      key: 'machine_hour_rate',
      value: 40,
      source: 'printer_explicit',
      source_currency: 'RUB',
      usable: true,
      missing_reason: null,
    }],
    reasons: [],
  },
  ...overrides,
} as PrinterEconomics);

const missingRateReadiness: PrinterEconomics['readiness'] = {
  version: 1,
  status: 'incomplete',
  money_currency: 'RUB',
  required_fields: [{
    key: 'machine_hour_rate',
    value: 0,
    source: 'none',
    source_currency: 'RUB',
    usable: false,
    missing_reason: 'non_positive',
  }],
  reasons: ['non_positive'],
};

const clearedUsdProfile = (): CalculatorProfileResponse => ({
  electricity_cost_per_kwh: 0,
  printer_power_w: 350,
  modeling_rate_per_hour: 0,
  postprocessing_rate_per_hour: 0,
  printing_rate_per_hour: 0,
  amortization_rate_per_hour: 0,
  overhead_percent: 20,
  markup_percent: 30,
  tax_rate_percent: 0,
  fixed_costs: 0,
  bed_prep_cost_per_print: 0,
  min_order_price: 0,
  round_to_nearest: 1,
  printer_purchase_price: 0,
  printer_useful_hours: 7000,
  maintenance_cost_per_hour: 0,
  power_hotend_w: 0,
  power_bed_w: 0,
  power_steppers_w: 0,
  power_electronics_w: 0,
  rounding_mode: 'up',
  seller_name: '',
  seller_inn: '',
  seller_phone: '',
  payment_terms: '',
  seller_registration_id: '',
  seller_tax_code: '',
  seller_address: '',
  seller_bank_details: '',
  quote_market: '',
  validity_days: 14,
  disclaimer_mode: 'not_offer',
  currency: 'USD',
  quote_number_prefix: '',
  updated_at: '2026-09-08T00:00:00Z',
  economics_readiness: {
    version: 1,
    status: 'incomplete',
    money_currency: 'USD',
    required_fields: [],
    reasons: ['non_positive'],
  },
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

  it('sends an explicit zero electricity tariff as known data', () => {
    const request = buildEstimateRequest({
      ...form,
      electricityCostPerKwh: 0,
    }, [], [], [], null);

    expect(request.electricity_cost_per_kwh).toBe(0);
    expect(request.printer_power_w).toBe(350);
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
      readiness: missingRateReadiness,
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
      readiness: missingRateReadiness,
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

describe('account economics autosave payloads', () => {
  it('maps one edited field to one API field and preserves zero', () => {
    expect(calculatorProfilePatchForField('printingRatePerHour', 0)).toEqual({
      printing_rate_per_hour: 0,
    });
    expect(calculatorProfilePatchForField('printerUsefulHours', 7000.8)).toEqual({
      printer_useful_hours: 7001,
    });
  });

  it('accumulates rapid edits without adding untouched defaults', () => {
    const patch = mergeCalculatorProfilePatches(
      calculatorProfilePatchForField('printerPowerW', 420),
      calculatorProfilePatchForField('maintenanceCostPerHour', 0),
    );

    expect(patch).toEqual({ printer_power_w: 420, maintenance_cost_per_hour: 0 });
  });

  it('does not let a late response replace a newer success or failure', () => {
    expect(isLatestCalculatorProfileRequest(1, 2)).toBe(false);
    expect(isLatestCalculatorProfileRequest(2, 2)).toBe(true);
  });

  it('serializes deferred writes so the newest value reaches persistence last', async () => {
    const starts: string[] = [];
    let releaseFirst!: () => void;
    const first = enqueueEconomicsSave(Promise.resolve(), () => new Promise<string>((resolve) => {
      starts.push('first');
      releaseFirst = () => resolve('first saved');
    }));
    const second = enqueueEconomicsSave(first.tail, async () => {
      starts.push('second');
      return 'second saved';
    });

    await vi.waitFor(() => expect(starts).toEqual(['first']));
    releaseFirst();
    await second.task;
    expect(starts).toEqual(['first', 'second']);
  });

  it('removes old-currency money from local state and the next estimate after currency save', () => {
    const rubForm = {
      ...form,
      modelingRatePerHour: 934,
      postprocessingRatePerHour: 100,
      printingRatePerHour: 170,
      amortizationRatePerHour: 16,
      maintenanceCostPerHour: 5,
      printerPurchasePrice: 90_000,
      fixedCosts: 300,
      bedPrepCostPerPrint: 20,
      minOrderPrice: 1_000,
    } as Parameters<typeof reconcileCalculatorProfileForm>[0];

    const usdForm = reconcileCalculatorProfileForm(rubForm, clearedUsdProfile());
    const request = buildEstimateRequest(usdForm);

    expect(usdForm).toMatchObject({
      modelingRatePerHour: 0,
      postprocessingRatePerHour: 0,
      printingRatePerHour: 0,
      amortizationRatePerHour: 0,
      maintenanceCostPerHour: 0,
      printerPurchasePrice: 0,
      fixedCosts: 0,
      bedPrepCostPerPrint: 0,
      minOrderPrice: 0,
    });
    expect(request.electricity_cost_per_kwh).toBe(0);
    expect(request.printing_rate_per_hour).toBeUndefined();
    expect(request.amortization_rate_per_hour).toBeUndefined();
    expect(request.fixed_costs).toBeUndefined();
    expect(request.bed_prep_cost_per_print).toBeUndefined();
    expect(request.min_order_price).toBeUndefined();
    expect(request).not.toMatchObject({
      printing_rate_per_hour: 170,
      amortization_rate_per_hour: 16,
      fixed_costs: 300,
      bed_prep_cost_per_print: 20,
      min_order_price: 1_000,
    });
  });

  it('rolls back the latest rejected currency change to the last confirmed currency', async () => {
    let visibleCurrency = 'USD';
    const confirmedCurrency = 'RUB';
    const requestSequence = 1;
    const latestSequence = 1;
    let rejectSave!: (error: Error) => void;
    const queued = enqueueEconomicsSave(Promise.resolve(), () => new Promise<CalculatorProfileResponse>(
      (_resolve, reject) => {
        rejectSave = reject;
      },
    ));

    const handled = queued.task.catch(() => {
      visibleCurrency = calculatorCurrencyAfterFailedSave(
        visibleCurrency,
        confirmedCurrency,
        true,
        requestSequence,
        latestSequence,
      );
    });
    await vi.waitFor(() => expect(rejectSave).toBeTypeOf('function'));
    rejectSave(new Error('currency rejected'));
    await handled;

    expect(visibleCurrency).toBe('RUB');
  });

  it('lets a newer noncurrency success reconcile currency after an older currency rejection', async () => {
    let visibleCurrency = 'USD';
    let confirmedCurrency = 'RUB';
    const latestSequence = 2;
    let rejectCurrency!: (error: Error) => void;
    const first = enqueueEconomicsSave(Promise.resolve(), () => new Promise<CalculatorProfileResponse>(
      (_resolve, reject) => {
        rejectCurrency = reject;
      },
    ));
    const second = enqueueEconomicsSave(first.tail, async () => ({
      ...clearedUsdProfile(),
      currency: 'RUB',
      economics_readiness: {
        ...clearedUsdProfile().economics_readiness,
        money_currency: 'RUB',
      },
    }));

    const firstHandled = first.task.catch(() => {
      visibleCurrency = calculatorCurrencyAfterFailedSave(
        visibleCurrency,
        confirmedCurrency,
        true,
        1,
        latestSequence,
      );
    });
    const secondHandled = second.task.then((profile) => {
      if (isLatestCalculatorProfileRequest(2, latestSequence)) {
        const serverCurrency = calculatorCurrencyFromProfile(profile);
        visibleCurrency = serverCurrency;
        confirmedCurrency = serverCurrency;
      }
    });

    await vi.waitFor(() => expect(rejectCurrency).toBeTypeOf('function'));
    rejectCurrency(new Error('older currency rejected'));
    await Promise.all([firstHandled, secondHandled]);

    expect(visibleCurrency).toBe('RUB');
    expect(confirmedCurrency).toBe('RUB');
  });
});

describe('economics result cautions', () => {
  it('uses readiness status instead of zero result lines', () => {
    expect(economicsReadinessResultNoteKey('partial', false)).toBe(
      'printerCost.readiness.resultPartial',
    );
    expect(economicsReadinessResultNoteKey('incomplete', false)).toBe(
      'printerCost.readiness.resultIncomplete',
    );
    expect(economicsReadinessResultNoteKey('configured', false)).toBeNull();
  });

  it('keeps an unavailable-readiness caution on a completed result', () => {
    expect(economicsReadinessResultNoteKey(null, true)).toBe(
      'printerCost.readiness.resultUnavailable',
    );
  });
});
