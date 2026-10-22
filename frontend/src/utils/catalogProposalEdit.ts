import type {
  CatalogCurationEvidence,
  CatalogCurationPreview,
  CatalogCurationSourceFact,
  CatalogCurationUnmappedFact,
  CatalogImportDraft,
  CatalogImportPlanRow,
  CatalogImportPreview,
  CatalogImportSheet,
} from '../types/api';

export type ProposalRow = Record<string, unknown>;

export const PROPOSAL_SHEETS: Array<{
  id: CatalogImportSheet;
  backendName: CatalogImportPlanRow['sheet'];
  labelKey: string;
}> = [
  { id: 'brands', backendName: 'Brands', labelKey: 'brands' },
  { id: 'filaments', backendName: 'Filaments', labelKey: 'filaments' },
  { id: 'brand_markets', backendName: 'BrandMarkets', labelKey: 'brandMarkets' },
  { id: 'filament_markets', backendName: 'FilamentMarkets', labelKey: 'filamentMarkets' },
  { id: 'presets', backendName: 'Presets', labelKey: 'presets' },
];

export const sheetBackendName = (sheet: CatalogImportSheet) =>
  (PROPOSAL_SHEETS.find((item) => item.id === sheet) ?? PROPOSAL_SHEETS[0]).backendName;

/** Stored by the importer but never shown or edited: they must round-trip untouched. */
export const HIDDEN_FIELDS = new Set(['_row', 'color_group_source', 'filler']);

export function cellText(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

export function isTruthyCell(value: unknown, fallback = false): boolean {
  if (value === undefined || value === null || value === '') return fallback;
  return ['true', '1', 'yes', 'да'].includes(cellText(value).toLowerCase());
}

export function listValues(value: unknown): string[] {
  if (Array.isArray(value)) return value.map(cellText).map((item) => item.trim()).filter(Boolean);
  if (typeof value !== 'string' || !value.trim()) return [];
  if (value.trim().startsWith('[')) {
    try {
      const parsed: unknown = JSON.parse(value);
      if (Array.isArray(parsed)) return parsed.map(cellText).map((item) => item.trim()).filter(Boolean);
    } catch { /* Keep the original cell text below. */ }
  }
  return value.split(';').map((item) => item.trim()).filter(Boolean);
}

export function filamentVisual(row: ProposalRow) {
  const rawColors = listValues(row.colors);
  const singleColor = cellText(row.color_hex).trim();
  const colors = (rawColors.length ? rawColors : [singleColor])
    .filter((color) => /^#(?:[\da-f]{3}|[\da-f]{6})$/i.test(color));
  const effects = listValues(row.effects);
  const filler = cellText(row.filler).trim();
  if (filler && filler !== 'none' && !effects.includes(filler)) effects.push(filler);
  return { colors, effects, finish: cellText(row.finish).trim(), colorType: cellText(row.color_type).trim() };
}

export function rowKey(sheet: CatalogImportSheet, row: ProposalRow): string {
  if (sheet === 'brand_markets' || sheet === 'filament_markets') {
    return `${String(row[sheet === 'brand_markets' ? 'brand_key' : 'filament_key'] ?? '').trim()}:${String(row.country ?? '').trim().toUpperCase()}`;
  }
  return String(row[sheet === 'brands' ? 'brand_key' : sheet === 'filaments' ? 'filament_key' : 'preset_key'] ?? '').trim();
}

/**
 * A number is stored only when it reads back exactly as typed. An entry such as "1.", "1.0" or "1.50"
 * stays text so the field keeps showing what was typed; the control normalizes it on blur.
 */
export function numberFromInput(text: string): number | string | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  return /^-?\d+(?:\.\d+)?$/.test(trimmed) && String(Number(trimmed)) === trimmed ? Number(trimmed) : text;
}

/** The value a finished number entry settles on; text that is not a plain number is kept as typed. */
export function settledNumber(text: string): number | string | null {
  const trimmed = text.trim();
  return /^-?\d+(?:\.\d+)?$/.test(trimmed) ? Number(trimmed) : numberFromInput(text);
}

export interface ProposalEditState {
  draft: CatalogImportDraft;
  evidence: CatalogCurationEvidence[];
  sourceFacts: CatalogCurationSourceFact[];
  unmappedFacts: CatalogCurationUnmappedFact[];
}

export interface CellEdit {
  index: number;
  field: string;
  value: unknown;
}

/**
 * The single path for every field edit, single or bulk. Untouched rows keep their identity,
 * and evidence follows a row only when an edit changes its key (for example a market country).
 */
export function applyCellEdits(
  state: ProposalEditState,
  sheet: CatalogImportSheet,
  edits: CellEdit[],
): ProposalEditState {
  const rows = state.draft[sheet];
  const nextRows = rows.slice();
  const renames = new Map<string, string>();
  const originalKeys = new Map<number, string>();
  for (const { index, field, value } of edits) {
    const row = nextRows[index];
    if (!row) continue;
    if (!originalKeys.has(index)) originalKeys.set(index, rowKey(sheet, rows[index]));
    nextRows[index] = { ...row, [field]: value };
  }
  if (nextRows.every((row, index) => row === rows[index])) return state;
  for (const [index, previousKey] of originalKeys) {
    const nextKey = rowKey(sheet, nextRows[index]);
    if (previousKey && nextKey && previousKey !== nextKey) renames.set(previousKey, nextKey);
  }
  const next: ProposalEditState = { ...state, draft: { ...state.draft, [sheet]: nextRows } };
  if (renames.size === 0) return next;
  const backendName = sheetBackendName(sheet);
  next.evidence = state.evidence.map((item) => item.sheet === backendName && renames.has(item.key)
    ? { ...item, key: renames.get(item.key) as string } : item);
  if (sheet === 'filaments') {
    next.sourceFacts = state.sourceFacts.map((item) => renames.has(item.filament_key)
      ? { ...item, filament_key: renames.get(item.filament_key) as string } : item);
    next.unmappedFacts = state.unmappedFacts.map((item) => renames.has(item.filament_key)
      ? { ...item, filament_key: renames.get(item.filament_key) as string } : item);
  }
  return next;
}

/** True when the edits would make two rows of the sheet share a key that was unique before. */
export function editsCollideKeys(
  rows: ProposalRow[],
  sheet: CatalogImportSheet,
  edits: CellEdit[],
): boolean {
  const next = rows.slice();
  for (const { index, field, value } of edits) {
    if (next[index]) next[index] = { ...next[index], [field]: value };
  }
  const count = (list: ProposalRow[]) => {
    const keys = new Map<string, number>();
    for (const row of list) {
      const key = rowKey(sheet, row);
      if (key) keys.set(key, (keys.get(key) ?? 0) + 1);
    }
    return keys;
  };
  const before = count(rows);
  for (const [key, total] of count(next)) {
    if (total > 1 && (before.get(key) ?? 0) < 2) return true;
  }
  return false;
}

/** Market rows live in their own draft sheet but are edited inside the record they belong to. */
export const MARKET_CHILD: Partial<Record<CatalogImportSheet, { sheet: CatalogImportSheet; keyField: string }>> = {
  brands: { sheet: 'brand_markets', keyField: 'brand_key' },
  filaments: { sheet: 'filament_markets', keyField: 'filament_key' },
};

/** Indices of the market rows that belong to one brand or filament. */
export function marketIndicesFor(draft: CatalogImportDraft, sheet: CatalogImportSheet, key: string): number[] {
  const child = MARKET_CHILD[sheet];
  if (!child || !key) return [];
  const indices: number[] = [];
  draft[child.sheet].forEach((row, index) => {
    if (cellText(row[child.keyField]).trim() === key) indices.push(index);
  });
  return indices;
}

export interface MarketGroup {
  id: string;
  brandKey: string;
  country: string;
  indices: number[];
}

/** Market rows grouped by the brand of their filament and the country; rows carry no brand_key. */
export function groupFilamentMarkets(draft: CatalogImportDraft): MarketGroup[] {
  const brandByFilament = new Map<string, string>();
  for (const filament of draft.filaments) {
    brandByFilament.set(String(filament.filament_key ?? '').trim(), String(filament.brand_key ?? '').trim());
  }
  const groups = new Map<string, MarketGroup>();
  draft.filament_markets.forEach((row, index) => {
    const brandKey = brandByFilament.get(String(row.filament_key ?? '').trim()) ?? '';
    const country = String(row.country ?? '').trim().toUpperCase();
    const id = `${brandKey}\u0000${country}`;
    const group = groups.get(id) ?? { id, brandKey, country, indices: [] };
    group.indices.push(index);
    groups.set(id, group);
  });
  return [...groups.values()];
}

export interface FieldSpread {
  /** Most common value; the group default shown in the editor. */
  value: unknown;
  uniform: boolean;
  exceptions: number[];
}

/** Compares one field across rows by its serialized value; rows without the field count as empty. */
export function fieldSpread(rows: ProposalRow[], indices: number[], field: string): FieldSpread {
  const tally = new Map<string, { value: unknown; indices: number[] }>();
  for (const index of indices) {
    const value = rows[index]?.[field];
    const bucketKey = JSON.stringify(value === undefined ? null : value);
    const bucket = tally.get(bucketKey) ?? { value, indices: [] };
    bucket.indices.push(index);
    tally.set(bucketKey, bucket);
  }
  let top: { value: unknown; indices: number[] } | undefined;
  for (const bucket of tally.values()) {
    if (!top || bucket.indices.length > top.indices.length) top = bucket;
  }
  return {
    value: top?.value,
    uniform: tally.size <= 1,
    exceptions: indices.filter((index) => !top?.indices.includes(index)),
  };
}

export interface FactCoverage {
  total: number;
  mapped: number;
  unsupported: number;
  unresolved: number;
}

export function factCoverageNeedsAttention(coverage: FactCoverage | undefined): boolean {
  if (!coverage || coverage.total === 0) return false;
  return !((coverage.mapped + coverage.unsupported) * 5 >= coverage.total * 4 && coverage.unresolved === 0);
}

export type ApplyOutcome = Record<'brands' | 'filaments' | 'markets' | 'presets', { create: number; update: number }> & { countries: number };

/** What applying the checked proposal would do, counted from the preview rows. */
export function previewOutcome(preview: CatalogImportPreview | CatalogCurationPreview | null): ApplyOutcome | null {
  if (!preview) return null;
  const outcome: ApplyOutcome = {
    brands: { create: 0, update: 0 }, filaments: { create: 0, update: 0 },
    markets: { create: 0, update: 0 }, presets: { create: 0, update: 0 }, countries: 0,
  };
  const countries = new Set<string>();
  for (const row of preview.rows) {
    if (row.status !== 'create' && row.status !== 'update') continue;
    if ((row.sheet === 'BrandMarkets' || row.sheet === 'FilamentMarkets') && row.key) {
      countries.add(row.key.slice(row.key.lastIndexOf(':') + 1));
    }
    const bucket = row.sheet === 'Brands' ? 'brands' : row.sheet === 'Filaments' ? 'filaments'
      : row.sheet === 'Presets' ? 'presets' : 'markets';
    outcome[bucket][row.status] += 1;
  }
  outcome.countries = countries.size;
  return outcome;
}

/** Adds one row to a sheet; every other row and the evidence stay as they are. */
export function appendRow(state: ProposalEditState, sheet: CatalogImportSheet, row: ProposalRow): ProposalEditState {
  return { ...state, draft: { ...state.draft, [sheet]: [...state.draft[sheet], row] } };
}

/** Removes exactly one row and the evidence that pointed at that row's key, nothing else. */
export function removeRowAt(state: ProposalEditState, sheet: CatalogImportSheet, index: number): ProposalEditState {
  const rows = state.draft[sheet];
  const row = rows[index];
  if (!row) return state;
  const key = rowKey(sheet, row);
  const duplicate = rows.some((other, i) => i !== index && rowKey(sheet, other) === key);
  const backendName = sheetBackendName(sheet);
  return {
    ...state,
    draft: { ...state.draft, [sheet]: rows.filter((_, i) => i !== index) },
    evidence: duplicate ? state.evidence : state.evidence.filter((item) => !(item.sheet === backendName && item.key === key)),
  };
}
