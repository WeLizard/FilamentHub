import { MODE_RANK, type SettingMode } from '../data/orcaFieldModes';
import type {
  OrcaPresetSchema,
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

// 0 on a bed-plate temperature means the filament does not support that plate.
const PLATE_TEMPERATURE_KEY = /_plate_temp(_initial_layer)?$/;
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
  if (PLATE_TEMPERATURE_KEY.test(key) && Number(text) === 0) return { kind: 'unsupported' };
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
    const tooltip = option ? (localizedOption(option, lang)?.tooltip ?? option.tooltip) : undefined;
    const fieldLabel = label ?? optionLabel(key, option, lang, true);
    return makeField(key, fieldLabel, tooltip, option);
  };

  const keyLabel = (entry: OrcaSchemaRowKey): string | undefined =>
    translated(entry.tr, lang) ?? entry.label;

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
            const field = resolveField(entry.key, keyLabel(entry));
            if (field) rows.push({ type: 'field', field });
          }
          continue;
        }

        const columns = entries.map((entry) => {
          return keyLabel(entry) ?? optionLabel(entry.key, schema.options[entry.key], lang, false);
        });
        const cells = entries.map((entry, index) => resolveField(entry.key, columns[index]));
        if (cells.every((cell) => cell === null)) continue;

        const rowTr = translated(row.tr, lang);
        const view = {
          label: rowTr?.label ?? row.label ?? columns.join(' / '),
          tooltip: rowTr?.tooltip ?? row.tooltip,
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
    const label = optionLabel(key, option, lang, true);
    const tooltip = option ? (localizedOption(option, lang)?.tooltip ?? option.tooltip) : undefined;
    other.push(makeField(key, label, tooltip, option));
  }

  return { pages, other, hiddenByMode };
}
