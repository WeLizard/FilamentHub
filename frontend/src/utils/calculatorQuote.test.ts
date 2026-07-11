import type { TFunction } from 'i18next';
import { describe, expect, it } from 'vitest';

import { buildEstimateRequest, buildQuoteLineItems } from '../pages/CalculatorPage';
import type { CalculatorEstimateResponse, CalculatorGcodeParseResponse } from '../types/api';
import { allocateRoundedTotal, quoteTitleFromFileName } from './calculatorQuote';

describe('quoteTitleFromFileName', () => {
  it('removes supported G-code suffixes without leaking slicer file syntax', () => {
    expect(quoteTitleFromFileName('Orca Head_PETG_6h24m_supps.gcode', 'Item')).toBe(
      'Orca Head_PETG_6h24m_supps',
    );
    expect(quoteTitleFromFileName('Metadata/plate_1.gcode.3mf', 'Item')).toBe('plate_1');
  });
});

describe('buildEstimateRequest', () => {
  it('omits an empty manual weight from the request', () => {
    const request = buildEstimateRequest({
      quantity: 1,
      roundToNearest: 10,
      roundingMode: 'up',
      weightG: 0,
    } as never);

    expect(request).not.toHaveProperty('weight_g');
  });

  it('does not mix legacy material fields into a material-lines request', () => {
    const request = buildEstimateRequest({
      quantity: 1,
      roundToNearest: 10,
      roundingMode: 'up',
      weightG: 36.68,
      supportsWeightG: 0,
      supportsLossCoefficient: 1.2,
      spoolPrice: 0,
      spoolWeightKg: 1,
      deliveryCost: 0,
    } as never, [{
      line_id: 'job:t0',
      job_key: 'job',
      tool_index: 0,
      label: 'PETG',
      weight_g: 36.68,
      spool_price: 1400,
      spool_weight_kg: 1,
      delivery_cost: 0,
      price_source: 'slicer',
      spool_id: null,
      filament_id: null,
      density_g_cm3: 0,
      selectionValue: 'manual',
      fileName: 'part.gcode',
      plateIndex: null,
      confidence: null,
      requiresSpoolChoice: false,
      priceResolved: true,
    } as never]);

    expect(request.material_lines).toHaveLength(1);
    expect(request.material_lines?.[0]?.density_g_cm3).toBeNull();
    expect(request).not.toHaveProperty('weight_g');
    expect(request).not.toHaveProperty('spool_price');
    expect(request).not.toHaveProperty('spool_weight_kg');
    expect(request).not.toHaveProperty('supports_loss_coefficient');
  });
});

describe('allocateRoundedTotal', () => {
  it('preserves the exact quote total after per-line rounding', () => {
    const values = allocateRoundedTotal(100, [1, 1, 1]);

    expect(values).toEqual([33.33, 33.33, 33.34]);
    expect(values.reduce((sum, value) => sum + value, 0)).toBe(100);
  });

  it('falls back to equal allocation when no useful weights exist', () => {
    expect(allocateRoundedTotal(10, [0, Number.NaN])).toEqual([5, 5]);
  });
});

const t = ((key: string, options?: { index?: number }) => {
  const values: Record<string, string> = {
    'profilePage.calculator.quoteDefaultItemTitle': 'Item',
    'profilePage.calculator.quoteWeight': 'Weight',
    'profilePage.calculator.quotePrintTime': 'Print time',
    'profilePage.calculator.grams': 'g',
    'profilePage.calc.h': 'h',
    'profilePage.calc.min': 'min',
  };
  if (key === 'profilePage.calculator.parsedPlateOption') return `Plate ${options?.index}`;
  return values[key] ?? key;
}) as unknown as TFunction;

const estimate = (overrides: Partial<CalculatorEstimateResponse> = {}): CalculatorEstimateResponse => ({
  cost_material: 30,
  cost_electricity: 10,
  cost_modeling: 0,
  cost_printing: 50,
  cost_postprocessing: 0,
  cost_amortization: 10,
  cost_bed_prep: 0,
  cost_tax: 0,
  cost_direct: 100,
  cost_overhead: 0,
  cost_before_markup: 100,
  cost_markup: 0,
  cost_first_part: 100,
  cost_subsequent_parts: 100,
  cost_total: 100,
  cost_final: 100,
  weight_kg: 0.03,
  time_hours: 1,
  quantity: 1,
  pricing_method: 'combined',
  ...overrides,
});

const parsed = (
  fileName: string,
  weightG: number,
  seconds: number,
  overrides: Partial<CalculatorGcodeParseResponse> = {},
): CalculatorGcodeParseResponse => ({
  file_name: fileName,
  file_size_bytes: 100,
  slicer_name: 'OrcaSlicer',
  slicer_version: '2.4.2',
  print_time_seconds: seconds,
  total_filament_weight_g: weightG,
  materials: [{ type: 'PETG', weight_g: weightG }],
  ...overrides,
});

describe('buildQuoteLineItems', () => {
  it('creates one quote row per uploaded G-code and preserves the total', () => {
    const result = estimate({
      material_line_costs: [
        { line_id: 'a', job_key: 'a', weight_g: 10, price_per_gram: 1, cost: 10, price_source: 'manual' },
        { line_id: 'b', job_key: 'b', weight_g: 20, price_per_gram: 1, cost: 20, price_source: 'manual' },
      ],
    });
    const jobs = [
      { key: 'a', parsed: parsed('first.gcode', 10, 1200) },
      { key: 'b', parsed: parsed('second.gcode.3mf', 20, 2400, { plate_index: 2 }) },
    ];

    const items = buildQuoteLineItems(t, { quantity: 1 } as never, result, jobs[0].parsed, null, jobs, []);

    expect(items).toHaveLength(2);
    expect(items[0].title).toBe('first');
    expect(items[1].title).toBe('second · Plate 2');
    expect(items.flatMap((item) => item.details).join(' ')).not.toContain('OrcaSlicer');
    expect(items.flatMap((item) => item.details)).toContain('PETG');
    expect(items.reduce((sum, item) => sum + item.totalPrice, 0)).toBe(100);
  });

  it('uses homogeneous EXCLUDE_OBJECT instances as commercial quantity', () => {
    const job = parsed('gears.gcode', 500, 14_400, {
      object_count: 200,
      object_groups: [{ name: 'Gear', count: 200, extrusion_share: 1 }],
    });

    const items = buildQuoteLineItems(t, { quantity: 1 } as never, estimate(), job, null, [{ key: 'job', parsed: job }], []);

    expect(items).toHaveLength(1);
    expect(items[0].title).toBe('Gear');
    expect(items[0].quantity).toBe(200);
    expect(items[0].unitPrice).toBe(0.5);
    expect(items[0].totalPrice).toBe(100);
  });

  it('keeps a mixed plate as one set until the user explicitly splits groups', () => {
    const job = parsed('mixed.gcode', 300, 7200, {
      object_count: 3,
      object_groups: [
        { name: 'Body', count: 1, extrusion_share: 0.7 },
        { name: 'Clip', count: 2, extrusion_share: 0.3 },
      ],
    });
    const jobs = [{ key: 'mixed', parsed: job }];
    const setItems = buildQuoteLineItems(
      t,
      { quantity: 1 } as never,
      estimate({ quantity: 2 }),
      job,
      null,
      jobs,
      [],
      [{ jobKey: 'mixed', repeats: 2, quoteMode: 'set', printTimeSeconds: 7200 }],
    );

    expect(setItems).toHaveLength(1);
    expect(setItems[0].title).toBe('mixed');
    expect(setItems[0].quantity).toBe(2);
  });

  it('splits a mixed plate by measured extrusion shares when requested', () => {
    const job = parsed('mixed.gcode', 300, 7200, {
      object_count: 3,
      object_groups: [
        { name: 'Body', count: 1, extrusion_share: 0.7 },
        { name: 'Clip', count: 2, extrusion_share: 0.3 },
      ],
    });
    const items = buildQuoteLineItems(
      t,
      { quantity: 1 } as never,
      estimate({ quantity: 6 }),
      job,
      null,
      [{ key: 'mixed', parsed: job }],
      [],
      [{ jobKey: 'mixed', repeats: 2, quoteMode: 'groups', printTimeSeconds: 7200 }],
    );

    expect(items.map((item) => [item.title, item.quantity])).toEqual([
      ['Body', 2],
      ['Clip', 4],
    ]);
    expect(items[0].totalPrice).toBe(70);
    expect(items[1].totalPrice).toBe(30);
    expect(items.reduce((sum, item) => sum + item.totalPrice, 0)).toBe(100);
  });
});
