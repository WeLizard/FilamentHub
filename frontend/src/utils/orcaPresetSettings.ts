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

export const readOrcaText = (
  source: OrcaPresetSettings | null | undefined,
  key: string,
): string => {
  const value = firstOrcaSetting(source, key);
  if (value == null) return '';
  const normalized = String(value);
  return normalized.trim().toLowerCase() === 'nil' ? '' : normalized;
};

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
