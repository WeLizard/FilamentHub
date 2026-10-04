export interface QuoteDisclosureLine {
  title: string;
  details: string[];
  quantity: number;
  unit?: string;
  unitPrice: number;
  totalPrice: number;
  sourceData?: Record<string, unknown> | null;
}

export interface QuoteDisclosureSnapshot {
  request_data?: Record<string, unknown> | null;
  result_data?: Record<string, unknown> | null;
  filament_snapshot?: Record<string, unknown> | null;
}

export interface QuoteTaxDisclosure {
  available: boolean;
  ratePercent: number | null;
  taxAmount: number | null;
  netAmount: number | null;
  taxBaseTotal: number | null;
}

const roundCents = (amount: number): number => Math.round((amount + Number.EPSILON) * 100);
const fromCents = (amount: number): number => amount / 100;
const finiteNonNegative = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value >= 0;
const scanningCost = (result: Record<string, unknown>): number =>
  finiteNonNegative(result.cost_scanning) ? result.cost_scanning : 0;

/** Binds disclosure to the base line quantities/prices while allowing title/details edits. */
export function quoteLinesFingerprint(lines: Array<Pick<QuoteDisclosureLine, 'quantity' | 'unit' | 'unitPrice'>>): string {
  return JSON.stringify(lines.map((line) => [
    Math.round(line.quantity * 1_000_000) / 1_000_000,
    line.unit ?? '',
    Math.round(line.unitPrice * 100),
  ]));
}

export function isQuoteDisclosureBoundToLines(
  snapshot: QuoteDisclosureSnapshot | null | undefined,
  lines: Array<Pick<QuoteDisclosureLine, 'quantity' | 'unit' | 'unitPrice'>>,
  expectedFingerprint: string | null | undefined,
  invalidated = false,
): boolean {
  const complete = getCompleteQuoteDisclosureSnapshot(snapshot);
  if (!complete || invalidated || lines.length === 0) return false;
  if (!expectedFingerprint || expectedFingerprint !== quoteLinesFingerprint(lines)) return false;
  const lineTotal = lines.reduce((sum, line) => sum + roundCents(line.quantity * line.unitPrice), 0);
  return roundCents(complete.result.cost_final as number) === lineTotal;
}

/** Snapshot fields are the only authority for disclosure. Unknown/partial snapshots fail closed. */
export function getCompleteQuoteDisclosureSnapshot(
  snapshot: QuoteDisclosureSnapshot | null | undefined,
): { result: Record<string, unknown>; request: Record<string, unknown> } | null {
  const result = snapshot?.result_data;
  const request = snapshot?.request_data;
  if (!result || !request) return null;
  const directFields = [
    'cost_material', 'cost_waste', 'cost_electricity', 'cost_modeling', 'cost_printing',
    'cost_postprocessing', 'cost_monitoring', 'cost_amortization', 'cost_bed_prep', 'cost_nozzle_wear',
  ];
  const resultFields = [...directFields, 'cost_direct', 'cost_overhead', 'cost_before_markup', 'cost_markup', 'cost_tax', 'cost_final'];
  if (!resultFields.every((key) => finiteNonNegative(result[key]))) return null;
  // Scanning is a flat customer price outside the direct costs; calculations saved before it existed carry none.
  if (result.cost_scanning !== undefined && result.cost_scanning !== null && !finiteNonNegative(result.cost_scanning)) return null;
  const taxRate = result.applied_tax_rate_percent;
  if (taxRate !== null && taxRate !== undefined && !finiteNonNegative(taxRate)) return null;
  if ((result.cost_tax as number) > 0 && !(typeof taxRate === 'number' && taxRate > 0)) return null;
  const directTotal = directFields.reduce((sum, key) => sum + (result[key] as number), 0);
  if (Math.abs(directTotal - (result.cost_direct as number)) > 0.05) return null;
  if ((result.cost_before_markup as number) + 0.05 < (result.cost_direct as number)) return null;
  for (const [service, amountKey, rateKey] of [
    ['modeling', 'cost_modeling', 'modeling_rate_per_hour'],
    ['postprocessing', 'cost_postprocessing', 'postprocessing_rate_per_hour'],
  ] as const) {
    if (!((result[amountKey] as number) > 0)) continue;
    if (!finiteNonNegative(request[rateKey]) || (request[rateKey] as number) <= 0) return null;
    if (!finiteNonNegative(request[`${service}_hours`]) || !finiteNonNegative(request[`${service}_minutes`])) return null;
  }
  return { result, request };
}

/** Total of the priced positions; the tagged customer-delivery row is not a position. */
export function sumQuotePositions(
  lines: Array<Pick<QuoteDisclosureLine, 'quantity' | 'unitPrice' | 'sourceData'>>,
): number {
  return fromCents(lines.reduce((sum, line) => (
    line.sourceData?.quote_component === 'customer_delivery' ? sum : sum + roundCents(line.quantity * line.unitPrice)
  ), 0));
}

export type QuoteWorkGroupKey = 'design' | 'printing' | 'postprocessing';

/** Facts shown under the printing row; each is present only when the snapshot states it reliably. */
export interface QuoteWorkCaption {
  parts?: number;
  material?: string;
  weightKg?: number;
  printHours?: number;
}

export interface QuoteWorkBreakdownEntry {
  key: QuoteWorkGroupKey | 'delivery';
  amount: number;
  caption?: QuoteWorkCaption;
}

const positiveNumber = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value > 0;

function buildPrintCaption(snapshot: QuoteDisclosureSnapshot): QuoteWorkCaption | undefined {
  const result = snapshot.result_data ?? {};
  const request = snapshot.request_data ?? {};
  const caption: QuoteWorkCaption = {};
  if (positiveNumber(result.quantity) && Number.isInteger(result.quantity)) caption.parts = result.quantity;
  const materialLines = Array.isArray(request.material_lines) ? request.material_lines : [];
  const materialType = snapshot.filament_snapshot?.material_type;
  if (materialLines.length <= 1 && typeof materialType === 'string' && materialType.trim()) {
    caption.material = materialType.trim();
  }
  if (positiveNumber(result.weight_kg)) caption.weightKg = result.weight_kg;
  // time_hours is one run; plates of a multi-plate job differ, so a total is stated for uniform runs only.
  const plates = Array.isArray(request.print_jobs) ? request.print_jobs : [];
  if (plates.length === 0 && positiveNumber(result.time_hours) && positiveNumber(result.print_runs)) {
    caption.printHours = result.time_hours * result.print_runs;
  }
  return Object.keys(caption).length > 0 ? caption : undefined;
}

/**
 * Customer-facing "by work" breakdown. The priced positions are spread over the work groups in
 * proportion to their direct costs (largest remainder, whole cents), so the rows sum exactly to
 * the document total. Overhead, markup and coefficients are never exposed; zero groups are omitted.
 */
export function buildQuoteWorkBreakdown(input: {
  snapshot: QuoteDisclosureSnapshot | null | undefined;
  /** Positions total without customer delivery; net of tax when the tax has its own line. */
  positionsTotal: number;
  /** Whether the positions already contain tax (false when the tax is shown as its own line). */
  positionsIncludeTax: boolean;
  customerDelivery?: number;
}): QuoteWorkBreakdownEntry[] | null {
  const complete = getCompleteQuoteDisclosureSnapshot(input.snapshot);
  if (!complete || !input.snapshot || !finiteNonNegative(input.positionsTotal)) return null;
  const { result } = complete;
  const sum = (keys: string[]) => keys.reduce((total, key) => total + (result[key] as number), 0);
  const groups: Array<{ key: QuoteWorkGroupKey; weight: number }> = [
    { key: 'design', weight: roundCents(sum(['cost_modeling'])) },
    {
      key: 'printing',
      weight: roundCents(sum([
        'cost_material', 'cost_waste', 'cost_electricity', 'cost_printing',
        'cost_amortization', 'cost_monitoring', 'cost_bed_prep', 'cost_nozzle_wear',
      ])),
    },
    { key: 'postprocessing', weight: roundCents(sum(['cost_postprocessing'])) },
  ];
  const weighted = groups.filter((group) => group.weight > 0);
  const weightTotal = weighted.reduce((total, group) => total + BigInt(group.weight), BigInt(0));
  // Scanning is not a direct cost: its exact customer price (taxed like the rest) goes to design.
  const taxRate = finiteNonNegative(result.applied_tax_rate_percent) ? result.applied_tax_rate_percent : 0;
  const scanningExact = scanningCost(result) * (input.positionsIncludeTax ? 1 + taxRate / 100 : 1);
  const positionsCents = roundCents(input.positionsTotal);
  const scanningCents = BigInt(weightTotal <= BigInt(0) && scanningExact > 0
    ? positionsCents
    : Math.min(roundCents(scanningExact), positionsCents));
  if (weightTotal <= BigInt(0) && scanningCents <= BigInt(0)) return null;
  const totalCents = BigInt(positionsCents) - scanningCents;
  const shares = weighted.map((group) => {
    const numerator = totalCents * BigInt(group.weight);
    return { key: group.key, cents: numerator / weightTotal, rest: numerator % weightTotal };
  });
  let leftover = totalCents - shares.reduce((total, share) => total + share.cents, BigInt(0));
  const byRest = shares.map((share, index) => ({ index, rest: share.rest }))
    .sort((a, b) => (a.rest === b.rest ? a.index - b.index : a.rest > b.rest ? -1 : 1));
  for (let i = 0; leftover > BigInt(0); i += 1, leftover -= BigInt(1)) {
    shares[byRest[i % byRest.length].index].cents += BigInt(1);
  }
  if (scanningCents > BigInt(0)) {
    const design = shares.find((share) => share.key === 'design');
    if (design) design.cents += scanningCents;
    else shares.unshift({ key: 'design', cents: scanningCents, rest: BigInt(0) });
  }
  const entries: QuoteWorkBreakdownEntry[] = [];
  for (const share of shares) {
    if (share.cents <= BigInt(0)) continue;
    const entry: QuoteWorkBreakdownEntry = { key: share.key, amount: fromCents(Number(share.cents)) };
    if (share.key === 'printing') {
      const caption = buildPrintCaption(input.snapshot);
      if (caption) entry.caption = caption;
    }
    entries.push(entry);
  }
  const delivery = roundCents(input.customerDelivery ?? 0);
  if (delivery > 0) entries.push({ key: 'delivery', amount: fromCents(delivery) });
  return entries;
}

/** Converts gross saved lines to a net subtotal only when every quantity can express exact cents. */
export function removeEmbeddedTaxFromLines(
  lines: QuoteDisclosureLine[],
  taxAmount: number,
): QuoteDisclosureLine[] | null {
  if (!finiteNonNegative(taxAmount) || taxAmount <= 0) return null;
  const totals = lines.map((line) => roundCents(line.quantity * line.unitPrice));
  const grossCents = totals.reduce((sum, cents) => sum + cents, 0);
  const taxCents = roundCents(taxAmount);
  if (taxCents >= grossCents || lines.some((line) => !Number.isFinite(line.quantity) || line.quantity <= 0)) return null;
  const reductions = totals.map((cents) => Math.floor(taxCents * cents / grossCents));
  let remainder = taxCents - reductions.reduce((sum, cents) => sum + cents, 0);
  const fractions = totals.map((cents, index) => ({ index, fraction: taxCents * cents / grossCents - reductions[index] }))
    .sort((a, b) => b.fraction - a.fraction || a.index - b.index);
  for (let index = 0; remainder > 0; index += 1, remainder -= 1) reductions[fractions[index % fractions.length].index] += 1;
  const netLines: QuoteDisclosureLine[] = [];
  for (let index = 0; index < lines.length; index += 1) {
    const targetCents = totals[index] - reductions[index];
    const unitCents = Math.round(targetCents / lines[index].quantity);
    if (Math.round(unitCents * lines[index].quantity) !== targetCents) return null;
    netLines.push({
      ...lines[index],
      details: [...lines[index].details],
      unitPrice: fromCents(unitCents),
      totalPrice: fromCents(targetCents),
      sourceData: {
        ...(lines[index].sourceData ?? {}),
        quote_gross_unit_price: lines[index].sourceData?.quote_gross_unit_price ?? lines[index].unitPrice,
        quote_gross_total_price: lines[index].sourceData?.quote_gross_total_price ?? lines[index].totalPrice,
      },
    });
  }
  const netCents = netLines.reduce((sum, line) => sum + roundCents(line.totalPrice), 0);
  return netCents + taxCents === grossCents ? netLines : null;
}

export function getSnapshotTaxDisclosure(
  snapshot: QuoteDisclosureSnapshot | null | undefined,
  total: number,
  untaxedCustomerDelivery = 0,
): QuoteTaxDisclosure {
  const complete = getCompleteQuoteDisclosureSnapshot(snapshot);
  if (!complete || !Number.isFinite(total) || total < 0 || !finiteNonNegative(untaxedCustomerDelivery)) {
    return { available: false, ratePercent: null, taxAmount: null, netAmount: null, taxBaseTotal: null };
  }
  const ratePercent = finiteNonNegative(complete.result.applied_tax_rate_percent)
    ? complete.result.applied_tax_rate_percent
    : null;
  const taxAmount = fromCents(roundCents(complete.result.cost_tax as number));
  const snapshotTotal = fromCents(roundCents(complete.result.cost_final as number));
  if (ratePercent === null || ratePercent <= 0 || taxAmount <= 0
      || fromCents(roundCents(snapshotTotal + untaxedCustomerDelivery)) !== fromCents(roundCents(total))
      || taxAmount > snapshotTotal || (ratePercent === 0 && taxAmount > 0)) {
    return { available: false, ratePercent: null, taxAmount: null, netAmount: null, taxBaseTotal: null };
  }
  return {
    available: true,
    ratePercent,
    taxAmount,
    netAmount: fromCents(roundCents(snapshotTotal) - roundCents(taxAmount)),
    taxBaseTotal: snapshotTotal,
  };
}

export interface CustomerDeliveryLine extends QuoteDisclosureLine {
  sourceData?: Record<string, unknown> | null;
}

/** Reverses only explicitly tagged presentation rows/price transformations. */
export function restoreQuoteBaseLines(lines: CustomerDeliveryLine[]): CustomerDeliveryLine[] {
  return lines.flatMap((line) => {
    const component = line.sourceData?.quote_component;
    if (component === 'customer_delivery' || component === 'modeling' || component === 'postprocessing') return [];
    const source = line.sourceData ?? {};
    const unitPrice = source.quote_base_unit_price ?? source.quote_gross_unit_price;
    const totalPrice = source.quote_base_total_price ?? source.quote_gross_total_price;
    return [{
      ...line,
      details: [...line.details],
      ...(typeof unitPrice === 'number' ? { unitPrice } : {}),
      ...(typeof totalPrice === 'number' ? { totalPrice } : {}),
      sourceData: { ...source },
    }];
  });
}

/** Replaces its tagged customer-delivery row; material procurement/shipping data is never used. */
export function replaceCustomerDeliveryLine(
  lines: CustomerDeliveryLine[],
  amount: number,
  title: string,
): CustomerDeliveryLine[] | null {
  if (!finiteNonNegative(amount)) return null;
  const retained = lines.filter((line) => line.sourceData?.quote_component !== 'customer_delivery')
    .map((line) => ({ ...line, details: [...line.details] }));
  const cents = roundCents(amount);
  if (cents > 0) retained.push({
    title, details: [], quantity: 1, unitPrice: fromCents(cents), totalPrice: fromCents(cents),
    sourceData: { quote_component: 'customer_delivery' },
  });
  return retained;
}

export interface DraftQuoteFinancialProjectionInput {
  lines: QuoteDisclosureLine[];
  snapshot: QuoteDisclosureSnapshot | null;
  sourceBound: boolean;
  invalidated: boolean;
  taxKind: 'tax' | 'vat';
  taxMode: 'hide' | 'included' | 'separate';
  savedTaxAmount: number;
  savedRowsAreNet: boolean;
  legacyTaxTotal: number;
  financiallyEdited: boolean;
  customerDeliveryAmount: number;
  deliveryTitle: string;
  baseLineFingerprint: string;
}

/** Single financial projection shared by quote editing and tests; display choices never add cost twice. */
export function projectDraftQuoteFinancials(input: DraftQuoteFinancialProjectionInput): {
  lines: QuoteDisclosureLine[];
  subtotal: number;
  taxTotal: number;
  grandTotal: number;
  taxDisclosureAmount: number;
  quoteDisclosure: Record<string, unknown>;
  taxSplitUnavailable: boolean;
} {
  const roundMoney = (value: number) => fromCents(roundCents(value));
  const baseTotal = roundMoney(input.lines.reduce((sum, line) => sum + roundMoney(line.quantity * line.unitPrice), 0));
  let lines = input.lines.map((line) => ({ ...line, details: [...line.details] }));
  const hasGrossRestoreMetadata = input.lines.some((line) => typeof line.sourceData?.quote_gross_unit_price === 'number'
    || typeof line.sourceData?.quote_base_unit_price === 'number');
  const savedRowsAlreadyNet = input.savedRowsAreNet && !hasGrossRestoreMetadata;
  const legacySeparateTax = !input.sourceBound && input.legacyTaxTotal > 0
    && (input.savedTaxAmount <= 0 || savedRowsAlreadyNet);
  const snapshotTax = input.sourceBound ? getSnapshotTaxDisclosure(input.snapshot, baseTotal) : null;
  const taxDisclosureAmount = snapshotTax?.available
    ? snapshotTax.taxAmount ?? 0
    : (input.financiallyEdited && !legacySeparateTax ? 0 : Math.max(0, input.savedTaxAmount));
  let taxTotal = 0;
  let taxSplitUnavailable = false;
  if (input.taxMode === 'separate' && taxDisclosureAmount > 0) {
    if (savedRowsAlreadyNet) taxTotal = taxDisclosureAmount;
    else {
      const netLines = removeEmbeddedTaxFromLines(lines, taxDisclosureAmount);
      if (netLines) { lines = netLines; taxTotal = taxDisclosureAmount; }
      else taxSplitUnavailable = true;
    }
  }
  if (legacySeparateTax) taxTotal = input.legacyTaxTotal;
  const withDelivery = replaceCustomerDeliveryLine(lines, input.customerDeliveryAmount, input.deliveryTitle);
  if (!withDelivery) return {
    lines, subtotal: baseTotal, taxTotal, grandTotal: roundMoney(baseTotal + taxTotal), taxDisclosureAmount,
    quoteDisclosure: {}, taxSplitUnavailable: true,
  };
  lines = withDelivery;
  const subtotal = roundMoney(lines.reduce((sum, line) => sum + roundMoney(line.quantity * line.unitPrice), 0));
  const grandTotal = roundMoney(subtotal + taxTotal);
  return {
    lines, subtotal, taxTotal, grandTotal, taxDisclosureAmount,
    quoteDisclosure: {
      taxKind: taxDisclosureAmount > 0 ? input.taxKind : null,
      taxMode: taxDisclosureAmount > 0 || legacySeparateTax ? input.taxMode : null,
      taxAmount: taxDisclosureAmount > 0 ? taxDisclosureAmount : legacySeparateTax ? input.legacyTaxTotal : 0,
      taxLinesAreNet: taxTotal > 0,
      customerDelivery: roundMoney(input.customerDeliveryAmount),
      invalidated: input.invalidated,
      baseLineFingerprint: input.baseLineFingerprint,
    },
    taxSplitUnavailable,
  };
}
