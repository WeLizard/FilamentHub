import type { SettingMode } from '../data/orcaFieldModes';

/** Shape of `data/orcaPresetSchema.<kind>.json`, produced by scripts/generate_orca_preset_schema.py. */

export type SchemaLanguage = 'ru' | 'zh';

export type OrcaOptionType =
  | 'int'
  | 'float'
  | 'percent'
  | 'bool'
  | 'enum'
  | 'string'
  | 'gcode'
  | 'multiline';

export interface OrcaOptionTranslation {
  label?: string;
  full_label?: string;
  tooltip?: string;
  unit?: string;
  labels?: string[];
}

export interface OrcaSchemaOption {
  type: OrcaOptionType;
  vector?: boolean;
  nullable?: boolean;
  label: string;
  full_label?: string;
  tooltip?: string;
  unit?: string;
  mode?: SettingMode;
  values?: string[];
  labels?: string[];
  gui?: string;
  min?: number;
  max?: number;
  tr?: Partial<Record<SchemaLanguage, OrcaOptionTranslation>>;
}

export interface OrcaSchemaRowKey {
  key: string;
  label?: string;
  tr?: Partial<Record<SchemaLanguage, string>>;
}

export interface OrcaSchemaCompositeRow {
  keys: Array<string | OrcaSchemaRowKey>;
  label?: string;
  tooltip?: string;
  widget?: boolean;
  tr?: Partial<Record<SchemaLanguage, { label?: string; tooltip?: string }>>;
}

export type OrcaSchemaRow = string | OrcaSchemaCompositeRow;

export interface OrcaSchemaGroup {
  title: string;
  tr?: Partial<Record<SchemaLanguage, string>>;
  rows: OrcaSchemaRow[];
}

export interface OrcaSchemaPage {
  title: string;
  tr?: Partial<Record<SchemaLanguage, string>>;
  groups: OrcaSchemaGroup[];
}

export interface OrcaPresetSchema {
  kind: string;
  pages: OrcaSchemaPage[];
  options: Record<string, OrcaSchemaOption>;
}

let filamentSchemaPromise: Promise<OrcaPresetSchema> | null = null;

/** The schema is ~150 KiB, so it is a separate chunk fetched on first use. */
export function loadFilamentPresetSchema(): Promise<OrcaPresetSchema> {
  if (!filamentSchemaPromise) {
    filamentSchemaPromise = import('../data/orcaPresetSchema.filament.json')
      .then((module) => module.default as unknown as OrcaPresetSchema)
      .catch((error: unknown) => {
        filamentSchemaPromise = null;
        throw error;
      });
  }
  return filamentSchemaPromise;
}
