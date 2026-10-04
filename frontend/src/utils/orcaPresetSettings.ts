import type { OrcaSchemaOption } from './orcaPresetSchema';

export type OrcaPresetSettings = Record<string, unknown>;

export const ORCA_MAX_NOZZLE_TEMPERATURE = 1500;
export const ORCA_MAX_BED_TEMPERATURE = 300;

export const normalizeOrcaSettingsForUi = (
  source: OrcaPresetSettings,
): Record<string, unknown[]> => Object.fromEntries(
  Object.entries(source).map(([key, value]) => [
    key,
    value == null ? [] : Array.isArray(value) ? value : [value],
  ]),
);

export const firstOrcaSetting = (
  source: OrcaPresetSettings | null | undefined,
  key: string,
): unknown => {
  const value = source?.[key];
  return Array.isArray(value) ? value[0] : value;
};

export const readOrcaNumber = (
  source: OrcaPresetSettings | null | undefined,
  key: string,
): number | null => {
  const value = firstOrcaSetting(source, key);
  if (value == null) return null;
  const normalized = String(value).trim();
  if (!normalized || normalized.toLowerCase() === 'nil') return null;
  const parsed = Number(normalized);
  return Number.isFinite(parsed) ? parsed : null;
};

export const ORCA_PLATE_TEMPERATURE_KEY = /_plate_temp(_initial_layer)?$/;

export const readOrcaPlateTemperatures = (
  source: OrcaPresetSettings | null | undefined,
): Record<string, number | ''> => Object.fromEntries(
  Object.keys(source ?? {})
    .filter((key) => ORCA_PLATE_TEMPERATURE_KEY.test(key))
    .map((key) => [key, readOrcaNumber(source, key) ?? '']),
);

export const readOrcaText = (
  source: OrcaPresetSettings | null | undefined,
  key: string,
): string => {
  const value = firstOrcaSetting(source, key);
  if (value == null) return '';
  const normalized = String(value);
  return normalized.trim().toLowerCase() === 'nil' ? '' : normalized;
};

export type OrcaExtraFieldKind = 'number' | 'percent' | 'text';

export const orcaExtraFieldKind = (option: OrcaSchemaOption | undefined): OrcaExtraFieldKind => {
  if (option?.type === 'percent') return 'percent';
  return option?.type === 'int' || option?.type === 'float' ? 'number' : 'text';
};

export const ORCA_EXTRA_FIELD_KEYS = [
  'filament_diameter',
  'filament_density',
  'required_nozzle_HRC',
  'filament_ironing_flow',
  'filament_ironing_spacing',
  'filament_ironing_inset',
  'filament_ironing_speed',
  'filament_tower_interface_pre_extrusion_dist',
  'filament_tower_interface_pre_extrusion_length',
  'filament_tower_ironing_area',
  'filament_tower_interface_purge_volume',
  'filament_tower_interface_print_temp',
  'filament_ramming_parameters',
];

export const MANUAL_OVERRIDES_KEY = 'fhub_manual_overrides';

export const readManualOverrides = (source: OrcaPresetSettings | null | undefined): string[] => {
  const raw = source?.[MANUAL_OVERRIDES_KEY];
  return Array.isArray(raw) ? raw.filter((key): key is string => typeof key === 'string') : [];
};

export const applyManualOverride = (
  target: OrcaPresetSettings,
  source: OrcaPresetSettings,
  key: string,
  manual: boolean,
): void => {
  const current = readManualOverrides(source);
  if (current.includes(key) === manual) return;
  const next = manual ? [...current, key].sort() : current.filter((entry) => entry !== key);
  if (next.length > 0) target[MANUAL_OVERRIDES_KEY] = next;
  else delete target[MANUAL_OVERRIDES_KEY];
};

export const readOrcaExtraFields = (
  source: OrcaPresetSettings | null | undefined,
): Record<string, string> => Object.fromEntries(
  ORCA_EXTRA_FIELD_KEYS.map((key) => [key, readOrcaText(source, key)]),
);

export const readOrcaBoolean = (
  source: OrcaPresetSettings | null | undefined,
  key: string,
): boolean | null => {
  const value = firstOrcaSetting(source, key);
  if (value == null) return null;
  if (typeof value === 'boolean') return value;
  if (typeof value === 'number') return value !== 0;

  const normalized = String(value).trim().toLowerCase();
  if (!normalized || normalized === 'nil') return null;
  if (['1', 'true', 'yes'].includes(normalized)) return true;
  if (['0', 'false', 'no'].includes(normalized)) return false;
  return null;
};

export const isOrcaBedTemperatureSentinel = (value: unknown): boolean => {
  if (value == null) return false;
  const normalized = String(value).trim().toLowerCase();
  return normalized === 'nil' || normalized === 'v';
};

export const cloneOrcaSettings = (
  source: OrcaPresetSettings | null | undefined,
): OrcaPresetSettings => source && typeof source === 'object' && !Array.isArray(source)
  ? { ...source }
  : {};

export const applyOrcaUiSetting = (
  target: OrcaPresetSettings,
  source: OrcaPresetSettings,
  key: string,
  value: string | number | unknown[] | null | undefined,
): void => {
  const hasOriginal = Object.prototype.hasOwnProperty.call(source, key);
  const original = firstOrcaSetting(source, key);
  if (value !== '' && value !== null && value !== undefined) {
    const nextFirst = Array.isArray(value) ? value[0] : value;
    if (hasOriginal && String(original) === String(nextFirst)) return;
    target[key] = Array.isArray(value) ? value : [String(value)];
    return;
  }
  if (String(original).trim().toLowerCase() === 'nil') return;
  delete target[key];
};

export const applyOrcaLinesFromUi = (
  target: OrcaPresetSettings,
  source: OrcaPresetSettings,
  key: string,
  value: string,
): void => {
  const original = source[key];
  const originalText = Array.isArray(original)
    ? original.map((line) => String(line)).join('\n')
    : original == null
      ? ''
      : String(original);
  if (Object.prototype.hasOwnProperty.call(source, key) && originalText === value) return;
  if (value === '') {
    delete target[key];
    return;
  }
  target[key] = value.split('\n');
};

export const applyOrcaBooleanFromUi = (
  target: OrcaPresetSettings,
  source: OrcaPresetSettings,
  key: string,
  value: boolean,
  inheritedDefault = false,
): void => {
  const hasOriginal = Object.prototype.hasOwnProperty.call(source, key);
  const originalValue = readOrcaBoolean(source, key);
  const effectiveOriginal = originalValue ?? inheritedDefault;

  if (value === effectiveOriginal) {
    if (!hasOriginal) delete target[key];
    return;
  }

  target[key] = [value ? '1' : '0'];
};

export const applyOrcaStructuredUiSetting = (
  target: OrcaPresetSettings,
  source: OrcaPresetSettings,
  key: string,
  currentUiValue: string,
  originalUiValue: string,
  normalizedValue: unknown,
): void => {
  if (
    Object.prototype.hasOwnProperty.call(source, key)
    && currentUiValue === originalUiValue
  ) {
    target[key] = source[key];
    return;
  }

  if (
    normalizedValue === ''
    || normalizedValue === null
    || normalizedValue === undefined
    || (Array.isArray(normalizedValue) && normalizedValue.length === 0)
  ) {
    delete target[key];
    return;
  }

  target[key] = normalizedValue;
};

export const formatOrcaFlowRatio = (percent: number): string => {
  const rendered = (percent / 100).toFixed(6).replace(/0+$/, '').replace(/\.$/, '');
  return rendered || '0';
};

interface FilamentCardIdentity {
  material_type?: string | null;
  brand_name?: string | null;
  color_hex?: string | null;
}

/**
 * Settings as the preset is delivered to Orca: the exporter overwrites type, vendor
 * and colour with the filament card's values (a missing card value keeps the stored one).
 */
export const withFilamentCardIdentity = (
  settings: OrcaPresetSettings,
  filament: FilamentCardIdentity | null | undefined,
): OrcaPresetSettings => {
  if (!filament) return settings;
  const projected: OrcaPresetSettings = { ...settings };
  if (filament.material_type) projected.filament_type = [filament.material_type];
  if (filament.brand_name) projected.filament_vendor = [filament.brand_name];
  if (filament.color_hex) {
    projected.default_filament_colour = [filament.color_hex];
    projected.filament_colour = [filament.color_hex];
  }
  return projected;
};
