import { describe, expect, it } from 'vitest';
import {
  buildQuoteWorkBreakdown,
  sumQuotePositions,
  getCompleteQuoteDisclosureSnapshot,
  getSnapshotTaxDisclosure,
  isQuoteDisclosureBoundToLines,
  removeEmbeddedTaxFromLines,
  projectDraftQuoteFinancials,
  quoteLinesFingerprint,
  replaceCustomerDeliveryLine,
  restoreQuoteBaseLines,
  type QuoteDisclosureSnapshot,
} from '../utils/quoteDisclosure';

const fullSnapshot = (overrides: Record<string, unknown> = {}): QuoteDisclosureSnapshot => ({
  request_data: {
    modeling_hours: 2, modeling_minutes: 30, modeling_rate_per_hour: 120,
    postprocessing_hours: 1, postprocessing_minutes: 0, postprocessing_rate_per_hour: 200,
    tax_rate_percent: 20,
  },
  result_data: {
    cost_material: 200, cost_waste: 0, cost_electricity: 100, cost_amortization: 100,
    cost_printing: 100, cost_modeling: 300, cost_postprocessing: 200, cost_monitoring: 0,
    cost_bed_prep: 0, cost_nozzle_wear: 0, cost_direct: 1000, cost_overhead: 0,
    cost_before_markup: 1000, cost_markup: 0,
    cost_tax: 200, cost_final: 1200, applied_tax_rate_percent: 20,
    ...overrides,
  },
});

// Captured from the local /api/v1/calculator/estimate response for the matching request below.
const actualEstimateSnapshot: QuoteDisclosureSnapshot = {
  request_data: {
    modeling_hours: 1, modeling_minutes: 30, modeling_rate_per_hour: 120,
    postprocessing_hours: 1, postprocessing_minutes: 0, postprocessing_rate_per_hour: 200,
    tax_rate_percent: 20,
  },
  result_data: {
    cost_material: 2.5, cost_waste: 0, cost_electricity: 0, cost_modeling: 180,
    cost_printing: 100, cost_postprocessing: 200, cost_monitoring: 0,
    cost_amortization: 0, cost_bed_prep: 0, cost_nozzle_wear: 0,
    cost_tax: 96.5, cost_direct: 482.5, cost_overhead: 0,
    cost_before_markup: 482.5, cost_markup: 0, cost_final: 579,
    applied_tax_rate_percent: 20,
  },
};

describe('quote customer-facing disclosures', () => {
  it('accepts and reconciles a real advanced estimate API snapshot', () => {
    expect(getCompleteQuoteDisclosureSnapshot(actualEstimateSnapshot)).not.toBeNull();
    const gross = [{ title: 'API estimate item', details: [], quantity: 1, unit: 'pcs', unitPrice: 579, totalPrice: 579 }];
    const projection = projectDraftQuoteFinancials({
      lines: gross,
      snapshot: actualEstimateSnapshot,
      sourceBound: true,
      invalidated: false,
      taxKind: 'tax',
      taxMode: 'separate',
      savedTaxAmount: 0,
      savedRowsAreNet: false,
      legacyTaxTotal: 0,
      financiallyEdited: false,
      customerDeliveryAmount: 0,
      deliveryTitle: 'Customer delivery',
      baseLineFingerprint: quoteLinesFingerprint(gross),
    });
    expect(projection.taxSplitUnavailable).toBe(false);
    expect(projection.taxTotal).toBe(96.5);
    expect(projection.subtotal).toBe(482.5);
    expect(projection.grandTotal).toBe(579);
    expect(projection.lines.map((line) => line.totalPrice)).toEqual([482.5]);
  });

  it('rejects stale same-total snapshots after line quantities or prices change', () => {
    const original = [{ quantity: 1, unit: 'pcs', unitPrice: 1200 }];
    const redistributed = [
      { quantity: 1, unit: 'pcs', unitPrice: 900 },
      { quantity: 1, unit: 'pcs', unitPrice: 300 },
    ];
    const originalFingerprint = quoteLinesFingerprint(original);
    expect(isQuoteDisclosureBoundToLines(fullSnapshot(), original, originalFingerprint)).toBe(true);
    expect(isQuoteDisclosureBoundToLines(fullSnapshot(), redistributed, originalFingerprint)).toBe(false);
    expect(isQuoteDisclosureBoundToLines(fullSnapshot(), original, undefined)).toBe(false);
    expect(isQuoteDisclosureBoundToLines(fullSnapshot(), original, undefined, true)).toBe(false);
  });

  it('preserves legacy separate tax through two successive draft save projections', () => {
    const legacyNetLine = [{
      title: 'Legacy item', details: [], quantity: 1, unit: 'pcs', unitPrice: 1000, totalPrice: 1000,
    }];
    const first = projectDraftQuoteFinancials({
      lines: legacyNetLine,
      snapshot: null,
      sourceBound: false,
      invalidated: true,
      taxKind: 'tax',
      taxMode: 'separate',
      savedTaxAmount: 0,
      savedRowsAreNet: false,
      legacyTaxTotal: 200,
      financiallyEdited: false,
      customerDeliveryAmount: 30,
      deliveryTitle: 'Customer delivery',
      baseLineFingerprint: quoteLinesFingerprint(legacyNetLine),
    });

    expect(first.lines.map((line) => line.totalPrice)).toEqual([1000, 30]);
    expect(first.taxTotal).toBe(200);
    expect(first.grandTotal).toBe(1230);
    expect(first.quoteDisclosure).toMatchObject({ taxAmount: 200, taxLinesAreNet: true, customerDelivery: 30 });

    // Re-open behavior: delivery is a tagged presentation row, and v2's persisted metadata is authoritative.
    const reopenedLines = restoreQuoteBaseLines(first.lines);
    const saved = first.quoteDisclosure;
    const second = projectDraftQuoteFinancials({
      lines: reopenedLines,
      snapshot: null,
      sourceBound: false,
      invalidated: saved.invalidated === true,
      taxKind: saved.taxKind === 'vat' ? 'vat' : 'tax',
      taxMode: saved.taxMode === 'included' || saved.taxMode === 'hide' ? saved.taxMode : 'separate',
      savedTaxAmount: Number(saved.taxAmount),
      savedRowsAreNet: saved.taxLinesAreNet === true,
      legacyTaxTotal: first.taxTotal,
      financiallyEdited: false,
      customerDeliveryAmount: Number(saved.customerDelivery),
      deliveryTitle: 'Customer delivery',
      baseLineFingerprint: String(saved.baseLineFingerprint),
    });
    expect(second.lines.map((line) => line.totalPrice)).toEqual([1000, 30]);
    expect(second.taxTotal).toBe(200);
    expect(second.grandTotal).toBe(1230);
    expect(second.quoteDisclosure).toMatchObject({ taxAmount: 200, taxLinesAreNet: true, customerDelivery: 30 });
  });

  it('projects included tax and customer delivery once without changing gross lines', () => {
    const lines = [{ title: 'Gross item', details: [], quantity: 1, unit: 'pcs', unitPrice: 1200, totalPrice: 1200 }];
    const projection = projectDraftQuoteFinancials({
      lines,
      snapshot: fullSnapshot(),
      sourceBound: true,
      invalidated: false,
      taxKind: 'vat',
      taxMode: 'included',
      savedTaxAmount: 0,
      savedRowsAreNet: false,
      legacyTaxTotal: 0,
      financiallyEdited: false,
      customerDeliveryAmount: 30,
      deliveryTitle: 'Customer delivery',
      baseLineFingerprint: quoteLinesFingerprint(lines),
    });
    expect(projection.lines.map((line) => line.totalPrice)).toEqual([1200, 30]);
    expect(projection.taxTotal).toBe(0);
    expect(projection.taxDisclosureAmount).toBe(200);
    expect(projection.grandTotal).toBe(1230);
  });

  it('invalidates saved tax when a user edits a previously net split back on gross-backed lines', () => {
    const gross = [{ title: 'Gross item', details: [], quantity: 1, unit: 'pcs', unitPrice: 1200, totalPrice: 1200 }];
    const initial = projectDraftQuoteFinancials({
      lines: gross,
      snapshot: fullSnapshot(),
      sourceBound: true,
      invalidated: false,
      taxKind: 'tax',
      taxMode: 'separate',
      savedTaxAmount: 0,
      savedRowsAreNet: false,
      legacyTaxTotal: 0,
      financiallyEdited: false,
      customerDeliveryAmount: 0,
      deliveryTitle: 'Customer delivery',
      baseLineFingerprint: quoteLinesFingerprint(gross),
    });
    expect(initial.lines[0]).toMatchObject({ unitPrice: 1000, sourceData: { quote_gross_unit_price: 1200 } });
    expect(initial.taxTotal).toBe(200);
    expect(initial.grandTotal).toBe(1200);

    const reopenedGross = restoreQuoteBaseLines(initial.lines);
    const editedGross = reopenedGross.map((line) => ({
      ...line, unitPrice: 1250, totalPrice: 1250, sourceData: {},
    }));
    // handleSubmit captures savedRowsAreNet=false from v1 restoration metadata before stripping it.
    const edited = projectDraftQuoteFinancials({
      lines: editedGross,
      snapshot: fullSnapshot(),
      sourceBound: false,
      invalidated: true,
      taxKind: 'tax',
      taxMode: 'separate',
      savedTaxAmount: 200,
      savedRowsAreNet: false,
      legacyTaxTotal: 200,
      financiallyEdited: true,
      customerDeliveryAmount: 0,
      deliveryTitle: 'Customer delivery',
      baseLineFingerprint: quoteLinesFingerprint(editedGross),
    });
    expect(edited.lines.map((line) => line.totalPrice)).toEqual([1250]);
    expect(edited.taxTotal).toBe(0);
    expect(edited.grandTotal).toBe(1250);
    expect(edited.quoteDisclosure).toMatchObject({ taxAmount: 0, taxLinesAreNet: false, invalidated: true });

    const third = projectDraftQuoteFinancials({
      lines: restoreQuoteBaseLines(edited.lines),
      snapshot: fullSnapshot(),
      sourceBound: false,
      invalidated: edited.quoteDisclosure.invalidated === true,
      taxKind: 'tax',
      taxMode: 'hide',
      savedTaxAmount: Number(edited.quoteDisclosure.taxAmount),
      savedRowsAreNet: edited.quoteDisclosure.taxLinesAreNet === true,
      legacyTaxTotal: edited.taxTotal,
      financiallyEdited: false,
      customerDeliveryAmount: 0,
      deliveryTitle: 'Customer delivery',
      baseLineFingerprint: String(edited.quoteDisclosure.baseLineFingerprint),
    });
    expect(third.grandTotal).toBe(1250);
    expect(third.taxTotal).toBe(0);
  });

  it('disables priced disclosure for legacy/incomplete snapshots instead of guessing', () => {
    const legacy = { result_data: { cost_modeling: 50, cost_final: 100 } };
    expect(getCompleteQuoteDisclosureSnapshot(legacy)).toBeNull();
    expect(buildQuoteWorkBreakdown({ snapshot: legacy, positionsTotal: 100, positionsIncludeTax: true })).toBeNull();
    expect(getSnapshotTaxDisclosure(legacy, 100).available).toBe(false);
  });

  it('shows only saved tax values and leaves a separately added customer delivery outside the tax base', () => {
    const disclosure = getSnapshotTaxDisclosure(fullSnapshot(), 1230, 30);
    expect(disclosure).toEqual({ available: true, ratePercent: 20, taxAmount: 200, netAmount: 1000, taxBaseTotal: 1200 });
    expect(getSnapshotTaxDisclosure(fullSnapshot(), 1230, 20).available).toBe(false);
  });

  it('replaces customer delivery idempotently without using material delivery fields', () => {
    const product = {
      title: 'Part', details: [], quantity: 1, unitPrice: 1200, totalPrice: 1200,
      sourceData: { material_delivery_cost: 55 },
    };
    const first = replaceCustomerDeliveryLine([product], 30, 'Customer delivery');
    const second = replaceCustomerDeliveryLine(first ?? [], 45, 'Customer delivery');
    expect(second).toHaveLength(2);
    expect(second?.[0]?.totalPrice).toBe(1200);
    expect(second?.[0].sourceData?.material_delivery_cost).toBe(55);
    expect(second?.[1]).toMatchObject({ quantity: 1, totalPrice: 45, sourceData: { quote_component: 'customer_delivery' } });
    expect(replaceCustomerDeliveryLine(second ?? [], 0, 'Customer delivery')).toHaveLength(1);
  });

  it('restores base prices and drops legacy service rows saved by the removed separate-rows option', () => {
    const legacyRows = [
      { title: 'Part', details: [], quantity: 1, unitPrice: 840, totalPrice: 840, sourceData: { quote_base_unit_price: 1200, quote_base_total_price: 1200 } },
      { title: 'Modeling', details: [], quantity: 1, unitPrice: 360, totalPrice: 360, sourceData: { quote_component: 'modeling' } },
    ];
    const net = removeEmbeddedTaxFromLines(legacyRows, 200);
    expect(net?.reduce((sum, line) => sum + line.totalPrice, 0)).toBe(1000);
    const withDelivery = replaceCustomerDeliveryLine(net ?? [], 30, 'Customer delivery');
    const reopened = restoreQuoteBaseLines(withDelivery ?? []);
    expect(reopened).toHaveLength(1);
    expect(reopened[0]).toMatchObject({ unitPrice: 1200, totalPrice: 1200 });
    expect(replaceCustomerDeliveryLine(reopened, 45, 'Customer delivery')?.filter((line) => line.sourceData?.quote_component === 'customer_delivery')).toHaveLength(1);
  });

  it('keeps delivery outside the saved tax base in both included and separate display modes', () => {
    const original = [{ title: 'Part', details: [], quantity: 1, unitPrice: 1200, totalPrice: 1200 }];
    const delivery = 30;
    const separateRows = removeEmbeddedTaxFromLines(original, 200);
    const separateWithDelivery = replaceCustomerDeliveryLine(separateRows ?? [], delivery, 'Customer delivery');
    expect(separateWithDelivery?.reduce((sum, line) => sum + Math.round(line.totalPrice * 100), 0)).toBe(103000);
    expect((separateWithDelivery?.reduce((sum, line) => sum + Math.round(line.totalPrice * 100), 0) ?? 0) + 20000).toBe(123000);
    const includedWithDelivery = replaceCustomerDeliveryLine(original, delivery, 'Customer delivery');
    expect(includedWithDelivery?.reduce((sum, line) => sum + Math.round(line.totalPrice * 100), 0)).toBe(123000);
  });

  describe('work breakdown', () => {
    const exampleSnapshot = (): QuoteDisclosureSnapshot => ({
      request_data: {
        modeling_hours: 1, modeling_minutes: 0, modeling_rate_per_hour: 3066.63,
        postprocessing_hours: 1, postprocessing_minutes: 0, postprocessing_rate_per_hour: 13.33,
        tax_rate_percent: 0,
      },
      result_data: {
        cost_material: 2803.94, cost_waste: 0, cost_electricity: 0, cost_amortization: 0,
        cost_printing: 0, cost_modeling: 3066.63, cost_postprocessing: 13.33, cost_monitoring: 0,
        cost_bed_prep: 0, cost_nozzle_wear: 0, cost_direct: 5883.9, cost_overhead: 0,
        cost_before_markup: 5883.9, cost_markup: 7206.1, cost_tax: 0, cost_final: 13090,
        quantity: 4, weight_kg: 1.15, time_hours: 6.5, print_runs: 4,
      },
      filament_snapshot: { material_type: 'PETG' },
    });

    it('rows sum to the document total to the cent and never expose overhead or markup', () => {
      const rows = buildQuoteWorkBreakdown({ snapshot: exampleSnapshot(), positionsTotal: 13090, positionsIncludeTax: true });
      expect(rows?.map((row) => row.key)).toEqual(['design', 'printing', 'postprocessing']);
      expect(Math.round((rows ?? []).reduce((sum, row) => sum + Math.round(row.amount * 100), 0))).toBe(1309000);
      expect(rows?.[1].caption).toEqual({ parts: 4, material: 'PETG', weightKg: 1.15, printHours: 26 });
    });

    it('keeps the sum exact for awkward cents, adds delivery on top and skips zero groups', () => {
      const snapshot = exampleSnapshot();
      Object.assign(snapshot.result_data as Record<string, unknown>, { cost_postprocessing: 0, cost_direct: 5870.57 });
      const rows = buildQuoteWorkBreakdown({ snapshot, positionsTotal: 10000.01, positionsIncludeTax: true, customerDelivery: 250 });
      expect(rows?.map((row) => row.key)).toEqual(['design', 'printing', 'delivery']);
      const positions = (rows ?? []).filter((row) => row.key !== 'delivery');
      expect(positions.reduce((sum, row) => sum + Math.round(row.amount * 100), 0)).toBe(1000001);
      expect(rows?.at(-1)?.amount).toBe(250);
    });

    it('adds the taxed scanning price to design exactly and leaves the rest split by direct costs', () => {
      const withScan = exampleSnapshot();
      Object.assign(withScan.result_data as Record<string, unknown>, {
        cost_scanning: 2000, applied_tax_rate_percent: 24, cost_tax: 3141.6, cost_final: 18711.6,
      });
      Object.assign(withScan.request_data as Record<string, unknown>, { scanning_price: 2000 });
      expect(getCompleteQuoteDisclosureSnapshot(withScan)).not.toBeNull();
      const positionsTotal = 16231.6 + 2480;
      const rows = buildQuoteWorkBreakdown({ snapshot: withScan, positionsTotal, positionsIncludeTax: true });
      const plain = buildQuoteWorkBreakdown({ snapshot: exampleSnapshot(), positionsTotal: 16231.6, positionsIncludeTax: true });
      expect(rows?.[0].key).toBe('design');
      expect(Math.round((rows?.[0].amount ?? 0) * 100) - Math.round((plain?.[0].amount ?? 0) * 100)).toBe(248000);
      expect((rows ?? []).reduce((sum, row) => sum + Math.round(row.amount * 100), 0)).toBe(Math.round(positionsTotal * 100));
    });

    it('uses the untaxed scanning price when the tax is a separate line, and caps it at the positions', () => {
      const withScan = exampleSnapshot();
      Object.assign(withScan.result_data as Record<string, unknown>, { cost_scanning: 2000, applied_tax_rate_percent: 24, cost_tax: 100 });
      const net = buildQuoteWorkBreakdown({ snapshot: withScan, positionsTotal: 15000, positionsIncludeTax: false });
      const gross = buildQuoteWorkBreakdown({ snapshot: withScan, positionsTotal: 15000, positionsIncludeTax: true });
      expect(Math.round((gross?.[0].amount ?? 0) * 100) - Math.round((net?.[0].amount ?? 0) * 100)).toBeGreaterThan(0);
      const tiny = buildQuoteWorkBreakdown({ snapshot: withScan, positionsTotal: 1000, positionsIncludeTax: false });
      expect((tiny ?? []).reduce((sum, row) => sum + Math.round(row.amount * 100), 0)).toBe(100000);
    });

    it('omits caption facts the snapshot cannot state reliably', () => {
      const multi = exampleSnapshot();
      Object.assign(multi.request_data as Record<string, unknown>, { print_jobs: [{}, {}], material_lines: [{}, {}] });
      expect(buildQuoteWorkBreakdown({ snapshot: multi, positionsTotal: 13090, positionsIncludeTax: true })?.[1].caption)
        .toEqual({ parts: 4, weightKg: 1.15 });
    });

    it('is unavailable for an incomplete snapshot and sums positions without the delivery row', () => {
      expect(buildQuoteWorkBreakdown({ snapshot: null, positionsTotal: 100, positionsIncludeTax: true })).toBeNull();
      expect(sumQuotePositions([
        { quantity: 2, unitPrice: 10.01 },
        { quantity: 1, unitPrice: 30, sourceData: { quote_component: 'customer_delivery' } },
      ])).toBe(20.02);
    });
  });
});
