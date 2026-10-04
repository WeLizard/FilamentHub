import { MODE_RANK, type SettingMode } from '../data/orcaFieldModes';
import { ORCA_PLATE_TEMPERATURE_KEY } from './orcaPresetSettings';
import type {
  OrcaPresetSchema,
  OrcaSchemaCompositeRow,
  OrcaSchemaOption,
  OrcaSchemaRow,
  OrcaSchemaRowKey,
  SchemaLanguage,
} from './orcaPresetSchema';

export type ViewLanguage = 'en' | SchemaLanguage;

/**
 * Keys that identify, link or sync a preset rather than configure the material.
 * Everything else stored in a preset must appear in the view, so this list is
 * deliberately explicit: a new Orca key can never be hidden by omission.
 * - envelope: Orca preset file metadata (see IDENTITY_KEYS in orcaslicer_exporter.py);
 * - compatible_printers*: the site manages printer compatibility itself and
 *   rewrites both keys on export (FILAMENT_MANAGED_PRINTER_COMPATIBILITY_KEYS);
 * - fhub_*, derived_from_*, enrichment: FilamentHub's own bookkeeping.
 */
const ORCA_SERVICE_KEYS: ReadonlySet<string> = new Set([
  'name',
  'type',
  'from',
  'version',
  'instantiation',
  'inherits',
  'setting_id',
  'filament_id',
  'filament_settings_id',
  '_comment',
  'is_custom_defined',
  'renamed_from',
  'compatible_printers',
  'compatible_printers_condition',
  'enrichment',
]);
const ORCA_SERVICE_KEY_PREFIXES = ['fhub_', 'derived_from_'];

export const isOrcaServiceKey = (key: string): boolean =>
  ORCA_SERVICE_KEYS.has(key) || ORCA_SERVICE_KEY_PREFIXES.some((prefix) => key.startsWith(prefix));

export type CellValue =
  | { kind: 'nil' }
  | { kind: 'empty' }
  | { kind: 'unsupported' }
  | { kind: 'bool'; value: boolean }
  | { kind: 'text'; text: string; unit?: string }
  | { kind: 'color'; text: string }
  | { kind: 'block'; text: string };

export interface FieldView {
  key: string;
  label: string;
  tooltip?: string;
  cells: CellValue[];
}

export interface TableRowView {
  label: string;
  tooltip?: string;
  cells: Array<FieldView | null>;
}

export type RowView =
  | { type: 'field'; field: FieldView }
  | { type: 'line'; label: string; tooltip?: string; fields: FieldView[] }
  | { type: 'table'; columns: string[]; rows: TableRowView[] };

export interface GroupView {
  title: string;
  rows: RowView[];
}

export interface PageView {
  id: string;
  title: string;
  groups: GroupView[];
}

export interface SchemaView {
  pages: PageView[];
  other: FieldView[];
  hiddenByMode: number;
}

export const OTHER_PAGE_ID = 'other';

const NIL_VALUE = /^nil%?$/i;
const HEX_COLOR = /^#[0-9a-f]{6}([0-9a-f]{2})?$/i;
const LONG_VALUE_LENGTH = 120;

export const humanizeOrcaKey = (key: string): string => {
  const words = key.replace(/_+/g, ' ').trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
};

/** Orca's list serialisation: `;`-separated tokens, quoted when they need escaping. */
export function splitOrcaStrings(text: string): string[] {
  const tokens: string[] = [];
  const length = text.length;
  let index = 0;
  while (index < length) {
    if (text[index] === '"') {
      let token = '';
      index += 1;
      while (index < length && text[index] !== '"') {
        if (text[index] === '\\' && index + 1 < length) {
          const escaped = text[index + 1];
          token += escaped === 'n' ? '\n' : escaped === 'r' ? '\r' : escaped;
          index += 2;
        } else {
          token += text[index];
          index += 1;
        }
      }
      index += 1;
      tokens.push(token);
    } else {
      const end = text.indexOf(';', index);
      const stop = end === -1 ? length : end;
      tokens.push(text.slice(index, stop));
      index = stop;
    }
    if (text[index] === ';') {
      index += 1;
      if (index === length) tokens.push('');
    }
  }
  return tokens;
}

/** Inverse of `splitOrcaStrings` for one token: quoted, with backslash, quote, newline and carriage return escaped. */
export function encodeOrcaString(text: string): string {
  const escaped = text.replace(/[\\"\n\r]/g, (char) => {
    if (char === '\n') return '\\n';
    if (char === '\r') return '\\r';
    return `\\${char}`;
  });
  return `"${escaped}"`;
}

/** First element of a stored string value, decoded when Orca serialised it with quotes. */
export function readOrcaSerializedText(source: Record<string, unknown> | null | undefined, key: string): string {
  const value = source?.[key];
  const first = Array.isArray(value) ? value[0] : value;
  if (first == null) return '';
  const text = String(first);
  return text.startsWith('"') ? (splitOrcaStrings(text)[0] ?? '') : text;
}

/** Writes an edited string value in the form the original element had; an unchanged value is left alone. */
export function applyOrcaSerializedText(
  target: Record<string, unknown>,
  source: Record<string, unknown>,
  key: string,
  value: string,
): void {
  const hasOriginal = Object.prototype.hasOwnProperty.call(source, key);
  if (value === readOrcaSerializedText(source, key)) return;
  if (value === '') {
    delete target[key];
    return;
  }
  const original = Array.isArray(source[key]) ? (source[key] as unknown[])[0] : source[key];
  const quoted = hasOriginal && String(original).startsWith('"');
  target[key] = [quoted ? encodeOrcaString(value) : value];
}

const isScalarList = (text: string): boolean =>
  text.includes(',') && text.split(',').every((token) => /^\s*(nil%?|-?\d+(\.\d+)?%?)\s*$/i.test(token));

/**
 * Elements of a stored value. The site keeps either a JSON array or one string in
 * Orca's own serialisation, where per-variant numbers are comma-joined.
 */
export function parseOrcaElements(option: OrcaSchemaOption | undefined, raw: unknown): string[] {
  if (raw === null || raw === undefined) return [];
  const items = Array.isArray(raw) ? raw : [raw];
  return items.flatMap((item): string[] => {
    const text = typeof item === 'object' && item !== null ? JSON.stringify(item) : String(item);
    switch (option?.type) {
      case 'int':
      case 'float':
      case 'percent':
      case 'bool':
      case 'enum':
        return text.split(',');
      case 'string':
        return splitOrcaStrings(text);
      case 'gcode':
      case 'multiline':
        return text.startsWith('"') ? splitOrcaStrings(text) : [text];
      default:
        if (text.startsWith('"')) return splitOrcaStrings(text);
        return isScalarList(text) ? text.split(',') : [text];
    }
  });
}

const translated = <T,>(tr: Partial<Record<SchemaLanguage, T>> | undefined, lang: ViewLanguage): T | undefined =>
  lang === 'en' ? undefined : tr?.[lang];

const localizedOption = (option: OrcaSchemaOption | undefined, lang: ViewLanguage) =>
  translated(option?.tr, lang);

const optionLabel = (
  key: string,
  option: OrcaSchemaOption | undefined,
  lang: ViewLanguage,
  preferFull: boolean,
): string => {
  const tr = localizedOption(option, lang);
  const label = preferFull
    ? (tr?.full_label ?? option?.full_label ?? tr?.label ?? option?.label)
    : (tr?.label ?? option?.label);
  return label || humanizeOrcaKey(key);
};

const optionUnit = (option: OrcaSchemaOption | undefined, lang: ViewLanguage): string | undefined => {
  const unit = localizedOption(option, lang)?.unit ?? option?.unit;
  return unit ? unit.replace('℃', '°C') : undefined;
};

/** The level Orca gives a field; a key the schema does not define stays out of Simple. */
export const schemaOptionMode = (schema: OrcaPresetSchema | undefined, key: string): SettingMode =>
  schema?.options[key]?.mode ?? 'advanced';

export function schemaGroupTitle(
  schema: OrcaPresetSchema,
  pageTitle: string,
  groupTitle: string,
  lang: ViewLanguage,
): string | undefined {
  const group = schema.pages
    .find((page) => page.title === pageTitle)
    ?.groups.find((candidate) => candidate.title === groupTitle);
  return group ? (translated(group.tr, lang) ?? group.title) : undefined;
}

export function schemaPageTitle(schema: OrcaPresetSchema, pageTitle: string, lang: ViewLanguage): string | undefined {
  const page = schema.pages.find((candidate) => candidate.title === pageTitle);
  return page ? (translated(page.tr, lang) ?? page.title) : undefined;
}

export interface SchemaOptionText {
  label: string;
  tooltip?: string;
  unit?: string;
}

export function schemaOptionText(
  schema: OrcaPresetSchema,
  key: string,
  lang: ViewLanguage,
  preferFull = false,
): SchemaOptionText {
  const option = schema.options[key];
  const tooltip = option ? (localizedOption(option, lang)?.tooltip ?? option.tooltip) : undefined;
  const unit = optionUnit(option, lang);
  return {
    label: optionLabel(key, option, lang, preferFull),
    ...(tooltip ? { tooltip } : {}),
    ...(unit ? { unit } : {}),
  };
}

const schemaKeyLabel = (entry: OrcaSchemaRowKey, lang: ViewLanguage): string | undefined =>
  translated(entry.tr, lang) ?? entry.label;

export function schemaRowText(
  row: OrcaSchemaCompositeRow,
  lang: ViewLanguage,
): { label?: string; tooltip?: string } {
  const tr = translated(row.tr, lang);
  return { label: tr?.label ?? row.label, tooltip: tr?.tooltip ?? row.tooltip };
}

function findCompositeRow(
  schema: OrcaPresetSchema,
  key: string,
): { row: OrcaSchemaCompositeRow; entry: OrcaSchemaRowKey } | undefined {
  for (const page of schema.pages) {
    for (const group of page.groups) {
      for (const row of group.rows) {
        if (typeof row === 'string' || row.widget) continue;
        const entries = row.keys.map((candidate): OrcaSchemaRowKey =>
          typeof candidate === 'string' ? { key: candidate } : candidate);
        const entry = entries.find((candidate) => candidate.key === key);
        if (entry) return { row, entry };
      }
    }
  }
  return undefined;
}

/** The line label and tooltip Orca gives the paired row a key belongs to. */
export function schemaRowTextForKey(
  schema: OrcaPresetSchema,
  key: string,
  lang: ViewLanguage,
): { label?: string; tooltip?: string } {
  const found = findCompositeRow(schema, key);
  return found ? schemaRowText(found.row, lang) : {};
}

/** The caption of one input inside a paired row, falling back to the option's own label. */
export function schemaEntryLabel(schema: OrcaPresetSchema, key: string, lang: ViewLanguage): string {
  const found = findCompositeRow(schema, key);
  return (found && schemaKeyLabel(found.entry, lang)) ?? schemaOptionText(schema, key, lang).label;
}

/** The choices of an enum setting: Orca's own values, shown with Orca's (translated) labels. */
export function schemaEnumOptions(
  schema: OrcaPresetSchema,
  key: string,
  lang: ViewLanguage,
): Array<{ value: string; label: string }> {
  const option = schema.options[key];
  const labels = localizedOption(option, lang)?.labels ?? option?.labels;
  return (option?.values ?? []).map((value, index) => ({ value, label: labels?.[index] ?? value }));
}

export interface BedPlateCell {
  key: string;
  mode: SettingMode;
}

export interface BedPlateRow {
  label: string;
  tooltip?: string;
  cells: BedPlateCell[];
}

export interface BedPlateTable {
  columns: string[];
  rows: BedPlateRow[];
}

/** The per-plate bed temperature rows of the Filament page: one row per plate, one cell per layer kind. */
export function buildBedPlateTable(schema: OrcaPresetSchema, lang: ViewLanguage): BedPlateTable | null {
  const group = schema.pages
    .find((page) => page.title === 'Filament')
    ?.groups.find((candidate) => candidate.title === 'Bed temperature');
  if (!group) return null;

  let columns: string[] = [];
  const rows: BedPlateRow[] = [];
  for (const row of group.rows) {
    if (typeof row === 'string' || row.widget) continue;
    const entries = row.keys.map((key): OrcaSchemaRowKey => (typeof key === 'string' ? { key } : key));
    if (entries.length < 2) continue;
    if (columns.length === 0) {
      columns = entries.map((entry) => schemaKeyLabel(entry, lang) ?? schemaOptionText(schema, entry.key, lang).label);
    }
    const text = schemaRowText(row, lang);
    rows.push({
      label: text.label ?? columns.join(' / '),
      ...(text.tooltip ? { tooltip: text.tooltip } : {}),
      cells: entries.map((entry) => ({ key: entry.key, mode: schemaOptionMode(schema, entry.key) })),
    });
  }
  return rows.length > 0 ? { columns, rows } : null;
}

function toCell(
  key: string,
  option: OrcaSchemaOption | undefined,
  element: string,
  lang: ViewLanguage,
): CellValue {
  const block = option?.type === 'gcode' || option?.type === 'multiline';
  const text = block ? element : element.trim();
  if (NIL_VALUE.test(text.trim())) return { kind: 'nil' };
  if (text.trim() === '') return { kind: 'empty' };

  if (option?.type === 'bool') {
    const normalized = text.toLowerCase();
    if (['1', 'true', 'yes'].includes(normalized)) return { kind: 'bool', value: true };
    if (['0', 'false', 'no'].includes(normalized)) return { kind: 'bool', value: false };
  }
  // 0 on a bed-plate temperature means the filament does not support that plate.
  if (ORCA_PLATE_TEMPERATURE_KEY.test(key) && Number(text) === 0) return { kind: 'unsupported' };
  if (option?.type === 'enum') {
    const index = option.values?.indexOf(text) ?? -1;
    if (index >= 0) {
      const label = localizedOption(option, lang)?.labels?.[index] ?? option.labels?.[index] ?? text;
      return { kind: 'text', text: label };
    }
  }
  if (option?.type === 'percent') return { kind: 'text', text: `${text.replace(/%$/, '')}%` };
  if (HEX_COLOR.test(text)) return { kind: 'color', text };
  if (block || text.includes('\n') || text.length > LONG_VALUE_LENGTH) return { kind: 'block', text };
  const unit = optionUnit(option, lang);
  return unit ? { kind: 'text', text, unit } : { kind: 'text', text };
}

/** One entry when every element (per extruder/variant) is the same, else the list. */
function collapseCells(cells: CellValue[]): CellValue[] {
  if (cells.length === 0) return [{ kind: 'empty' }];
  const first = JSON.stringify(cells[0]);
  return cells.every((cell) => JSON.stringify(cell) === first) ? [cells[0]] : cells;
}

export function buildSchemaView(
  schema: OrcaPresetSchema,
  settings: Record<string, unknown>,
  mode: SettingMode,
  lang: ViewLanguage,
): SchemaView {
  const consumed = new Set<string>();
  let hiddenByMode = 0;

  const isPresent = (key: string) =>
    Object.prototype.hasOwnProperty.call(settings, key) && !isOrcaServiceKey(key);

  // A key the schema does not define has no level of its own; Advanced keeps it out of Simple.
  const isVisible = (option: OrcaSchemaOption | undefined) =>
    MODE_RANK[option?.mode ?? 'advanced'] <= MODE_RANK[mode];

  const makeField = (
    key: string,
    label: string,
    tooltip: string | undefined,
    option: OrcaSchemaOption | undefined,
  ): FieldView => {
    const cells = collapseCells(
      parseOrcaElements(option, settings[key]).map((element) => toCell(key, option, element, lang)),
    );
    return { key, label, ...(tooltip ? { tooltip } : {}), cells };
  };

  // Returns null when absent, a service key, or hidden by the current level.
  const resolveField = (key: string, label?: string): FieldView | null => {
    consumed.add(key);
    if (!isPresent(key)) return null;
    const option = schema.options[key];
    if (!isVisible(option)) {
      hiddenByMode += 1;
      return null;
    }
    const text = schemaOptionText(schema, key, lang, true);
    return makeField(key, label ?? text.label, text.tooltip, option);
  };

  const pages: PageView[] = [];
  schema.pages.forEach((page, pageIndex) => {
    const groups: GroupView[] = [];
    for (const group of page.groups) {
      const rows: RowView[] = [];
      let run: Array<{ label: string; tooltip?: string; columns: string[]; cells: Array<FieldView | null> }> = [];

      const flushRun = () => {
        if (run.length >= 2) {
          rows.push({
            type: 'table',
            columns: run[0].columns,
            rows: run.map(({ label, tooltip, cells }) => ({ label, tooltip, cells })),
          });
        } else if (run.length === 1) {
          const [only] = run;
          const fields = only.cells
            .map((cell, index) => (cell ? { ...cell, label: only.columns[index] } : null))
            .filter((cell): cell is FieldView => cell !== null);
          rows.push({ type: 'line', label: only.label, tooltip: only.tooltip, fields });
        }
        run = [];
      };

      for (const row of group.rows as OrcaSchemaRow[]) {
        const entries: OrcaSchemaRowKey[] =
          typeof row === 'string' ? [{ key: row }] : row.keys.map((k) => (typeof k === 'string' ? { key: k } : k));
        const composite = typeof row !== 'string' && !row.widget && entries.length > 1;

        if (!composite) {
          flushRun();
          for (const entry of entries) {
            const field = resolveField(entry.key, schemaKeyLabel(entry, lang));
            if (field) rows.push({ type: 'field', field });
          }
          continue;
        }

        const columns = entries.map((entry) => {
          return schemaKeyLabel(entry, lang) ?? optionLabel(entry.key, schema.options[entry.key], lang, false);
        });
        const cells = entries.map((entry, index) => resolveField(entry.key, columns[index]));
        if (cells.every((cell) => cell === null)) continue;

        const rowText = schemaRowText(row, lang);
        const view = {
          label: rowText.label ?? columns.join(' / '),
          tooltip: rowText.tooltip,
          columns,
          cells,
        };
        if (run.length > 0 && run[0].columns.join('\u0000') !== columns.join('\u0000')) flushRun();
        run.push(view);
      }
      flushRun();

      if (rows.length > 0) groups.push({ title: translated(group.tr, lang) ?? group.title, rows });
    }
    if (groups.length > 0) {
      pages.push({
        id: String(pageIndex),
        title: translated(page.tr, lang) ?? page.title,
        groups,
      });
    }
  });

  const other: FieldView[] = [];
  for (const key of Object.keys(settings).sort()) {
    if (consumed.has(key) || !isPresent(key)) continue;
    const option = schema.options[key];
    if (!isVisible(option)) {
      hiddenByMode += 1;
      continue;
    }
    const text = schemaOptionText(schema, key, lang, true);
    other.push(makeField(key, text.label, text.tooltip, option));
  }

  return { pages, other, hiddenByMode };
}
